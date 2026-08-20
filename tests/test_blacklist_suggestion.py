import tempfile
from pathlib import Path

from main import append_to_company_blacklist


def test_append_to_company_blacklist_inserts_after_existing_key():
    with tempfile.TemporaryDirectory() as tmp:
        config_file = Path(tmp) / "work_preferences.yaml"
        config_file.write_text(
            "positions:\n"
            "  - Software engineer\n"
            "\n"
            "company_blacklist:\n"
            "  - wayfair\n"
            "\n"
            "title_blacklist:\n"
            "  - word1\n",
            encoding="utf-8",
        )

        append_to_company_blacklist(config_file, ["Ghosted Inc"])

        text = config_file.read_text(encoding="utf-8")
        assert "  - wayfair" in text
        assert "  - Ghosted Inc" in text
        assert "title_blacklist:" in text
        lines = text.splitlines()
        blacklist_index = lines.index("company_blacklist:")
        assert lines[blacklist_index + 1] == "  - Ghosted Inc"


def test_append_to_company_blacklist_creates_key_if_missing():
    with tempfile.TemporaryDirectory() as tmp:
        config_file = Path(tmp) / "work_preferences.yaml"
        config_file.write_text("positions:\n  - QA\n", encoding="utf-8")

        append_to_company_blacklist(config_file, ["Acme"])

        text = config_file.read_text(encoding="utf-8")
        assert "company_blacklist:" in text
        assert "  - Acme" in text


if __name__ == "__main__":
    test_append_to_company_blacklist_inserts_after_existing_key()
    test_append_to_company_blacklist_creates_key_if_missing()
    print("All tests passed.")
