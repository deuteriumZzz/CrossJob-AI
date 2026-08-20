import tempfile
from pathlib import Path

from src.config_patch import set_source_field


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


if __name__ == "__main__":
    test_set_source_field_updates_existing_value()
    test_set_source_field_adds_field_to_existing_block()
    test_set_source_field_creates_block_if_missing()
    print("All tests passed.")
