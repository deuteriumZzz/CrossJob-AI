import tempfile
from pathlib import Path

from src.config_patch import (
    set_list_field,
    set_source_field,
    set_source_list_field,
    set_top_level_field,
    unset_source_field,
)


def test_set_source_field_updates_existing_value():
    with tempfile.TemporaryDirectory() as tmp:
        config_file = Path(tmp) / "work_preferences.yaml"
        config_file.write_text(
            "positions:\n"
            "  - QA\n"
            "\n"
            "headhunter:\n"
            "  auto_apply: false\n"
            '  resume_id: "abc"\n'
            "\n"
            "superjob:\n"
            "  auto_apply: false\n",
            encoding="utf-8",
        )

        set_source_field(config_file, "headhunter", "auto_apply", True)

        text = config_file.read_text(encoding="utf-8")
        lines = text.splitlines()
        hh_index = lines.index("headhunter:")
        assert lines[hh_index + 1] == "  auto_apply: true"
        # соседний блок и остальные поля не тронуты
        assert '  resume_id: "abc"' in text
        assert "superjob:\n  auto_apply: false" in text


def test_set_source_field_adds_field_to_existing_block():
    with tempfile.TemporaryDirectory() as tmp:
        config_file = Path(tmp) / "work_preferences.yaml"
        config_file.write_text(
            "headhunter:\n"
            "  auto_apply: false\n"
            "\n"
            "superjob:\n"
            "  auto_apply: false\n",
            encoding="utf-8",
        )

        set_source_field(config_file, "headhunter", "interval_hours", 3)

        text = config_file.read_text(encoding="utf-8")
        hh_block = text.split("superjob:")[0]
        assert "interval_hours: 3" in hh_block


def test_set_source_field_creates_block_if_missing():
    with tempfile.TemporaryDirectory() as tmp:
        config_file = Path(tmp) / "work_preferences.yaml"
        config_file.write_text("positions:\n  - QA\n", encoding="utf-8")

        set_source_field(config_file, "geekjob", "schedule_enabled", True)

        text = config_file.read_text(encoding="utf-8")
        assert "geekjob:" in text
        assert "schedule_enabled: true" in text


def test_unset_source_field_removes_existing_value():
    with tempfile.TemporaryDirectory() as tmp:
        config_file = Path(tmp) / "work_preferences.yaml"
        config_file.write_text(
            "headhunter:\n"
            "  auto_apply: false\n"
            "  daily_application_limit: 40\n"
            "\n"
            "superjob:\n"
            "  daily_application_limit: 12\n",
            encoding="utf-8",
        )

        unset_source_field(
            config_file, "headhunter", "daily_application_limit"
        )

        text = config_file.read_text(encoding="utf-8")
        hh_block = text.split("superjob:")[0]
        assert "daily_application_limit" not in hh_block
        assert "auto_apply: false" in hh_block
        # соседний блок не тронут
        assert "superjob:\n  daily_application_limit: 12" in text


def test_unset_source_field_noop_when_field_missing():
    with tempfile.TemporaryDirectory() as tmp:
        config_file = Path(tmp) / "work_preferences.yaml"
        original = "headhunter:\n  auto_apply: false\n"
        config_file.write_text(original, encoding="utf-8")

        unset_source_field(
            config_file, "headhunter", "daily_application_limit"
        )

        assert config_file.read_text(encoding="utf-8") == original


def test_unset_source_field_noop_when_block_missing():
    with tempfile.TemporaryDirectory() as tmp:
        config_file = Path(tmp) / "work_preferences.yaml"
        original = "positions:\n  - QA\n"
        config_file.write_text(original, encoding="utf-8")

        unset_source_field(config_file, "linkedin", "daily_application_limit")

        assert config_file.read_text(encoding="utf-8") == original


def test_set_top_level_field_updates_existing_value():
    with tempfile.TemporaryDirectory() as tmp:
        config_file = Path(tmp) / "secrets.yaml"
        config_file.write_text(
            "llm_api_key: 'old-key'\n\nheadhunter:\n  client_id: ''\n",
            encoding="utf-8",
        )

        set_top_level_field(config_file, "llm_api_key", "sk-new")

        text = config_file.read_text(encoding="utf-8")
        assert "llm_api_key: 'sk-new'" in text
        # остальной файл не тронут
        assert "headhunter:\n  client_id: ''" in text


def test_set_top_level_field_inserts_when_missing():
    with tempfile.TemporaryDirectory() as tmp:
        config_file = Path(tmp) / "secrets.yaml"
        config_file.write_text(
            "headhunter:\n  client_id: ''\n", encoding="utf-8"
        )

        set_top_level_field(config_file, "llm_api_key", "sk-fresh")

        text = config_file.read_text(encoding="utf-8")
        assert text.splitlines()[0] == "llm_api_key: 'sk-fresh'"


def test_set_top_level_field_escapes_single_quotes():
    with tempfile.TemporaryDirectory() as tmp:
        config_file = Path(tmp) / "secrets.yaml"
        config_file.write_text("llm_api_key: ''\n", encoding="utf-8")

        set_top_level_field(config_file, "llm_api_key", "sk-o'brien")

        text = config_file.read_text(encoding="utf-8")
        assert "llm_api_key: 'sk-o''brien'" in text


def test_set_list_field_replaces_existing_list():
    with tempfile.TemporaryDirectory() as tmp:
        config_file = Path(tmp) / "work_preferences.yaml"
        config_file.write_text(
            "positions:\n"
            "  - Software engineer\n"
            "\n"
            "locations:\n"
            "  - Germany\n",
            encoding="utf-8",
        )

        set_list_field(config_file, "positions", ["Backend developer"])

        text = config_file.read_text(encoding="utf-8")
        assert "Software engineer" not in text
        assert "  - 'Backend developer'" in text
        # соседний блок не тронут
        assert "locations:\n  - Germany" in text


def test_set_list_field_empty_list_writes_inline_brackets():
    with tempfile.TemporaryDirectory() as tmp:
        config_file = Path(tmp) / "work_preferences.yaml"
        config_file.write_text(
            "company_blacklist:\n  - wayfair\n  - Crossover\n",
            encoding="utf-8",
        )

        set_list_field(config_file, "company_blacklist", [])

        text = config_file.read_text(encoding="utf-8")
        assert text.strip() == "company_blacklist: []"


def test_set_list_field_creates_block_if_missing():
    with tempfile.TemporaryDirectory() as tmp:
        config_file = Path(tmp) / "work_preferences.yaml"
        config_file.write_text("positions:\n  - QA\n", encoding="utf-8")

        set_list_field(config_file, "title_blacklist", ["intern"])

        text = config_file.read_text(encoding="utf-8")
        assert "title_blacklist:\n  - 'intern'" in text


def test_set_list_field_escapes_single_quotes():
    with tempfile.TemporaryDirectory() as tmp:
        config_file = Path(tmp) / "work_preferences.yaml"
        config_file.write_text("positions:\n  - QA\n", encoding="utf-8")

        set_list_field(config_file, "positions", ["O'Brien Inc"])

        text = config_file.read_text(encoding="utf-8")
        assert "  - 'O''Brien Inc'" in text


def test_set_source_list_field_replaces_existing_nested_list():
    with tempfile.TemporaryDirectory() as tmp:
        config_file = Path(tmp) / "work_preferences.yaml"
        config_file.write_text(
            "telegram:\n"
            "  channels:\n"
            "    - old_channel\n"
            "  messages_per_channel: 100\n"
            "\n"
            "linkedin:\n"
            "  auto_apply: false\n",
            encoding="utf-8",
        )

        set_source_list_field(
            config_file, "telegram", "channels", ["chan_one", "chan_two"]
        )

        text = config_file.read_text(encoding="utf-8")
        assert "old_channel" not in text
        assert "    - 'chan_one'" in text
        assert "    - 'chan_two'" in text
        # соседнее поле того же блока и другой блок не тронуты
        assert "  messages_per_channel: 100" in text
        assert "linkedin:\n  auto_apply: false" in text


def test_set_source_list_field_creates_key_if_missing():
    with tempfile.TemporaryDirectory() as tmp:
        config_file = Path(tmp) / "work_preferences.yaml"
        config_file.write_text(
            "telegram:\n  messages_per_channel: 100\n", encoding="utf-8"
        )

        set_source_list_field(config_file, "telegram", "channels", ["c1"])

        text = config_file.read_text(encoding="utf-8")
        assert "channels:\n    - 'c1'" in text
        assert "messages_per_channel: 100" in text


def test_set_source_list_field_creates_block_if_missing():
    with tempfile.TemporaryDirectory() as tmp:
        config_file = Path(tmp) / "work_preferences.yaml"
        config_file.write_text("positions:\n  - QA\n", encoding="utf-8")

        set_source_list_field(config_file, "telegram", "channels", ["c1"])

        text = config_file.read_text(encoding="utf-8")
        assert "telegram:\n  channels:\n    - 'c1'" in text


if __name__ == "__main__":
    test_set_source_field_updates_existing_value()
    test_set_source_field_adds_field_to_existing_block()
    test_set_source_field_creates_block_if_missing()
    test_unset_source_field_removes_existing_value()
    test_unset_source_field_noop_when_field_missing()
    test_unset_source_field_noop_when_block_missing()
    test_set_top_level_field_updates_existing_value()
    test_set_top_level_field_inserts_when_missing()
    test_set_top_level_field_escapes_single_quotes()
    test_set_list_field_replaces_existing_list()
    test_set_list_field_empty_list_writes_inline_brackets()
    test_set_list_field_creates_block_if_missing()
    test_set_list_field_escapes_single_quotes()
    test_set_source_list_field_replaces_existing_nested_list()
    test_set_source_list_field_creates_key_if_missing()
    test_set_source_list_field_creates_block_if_missing()
    print("All tests passed.")
