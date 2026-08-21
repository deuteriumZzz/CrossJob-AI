import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

import main


def test_force_refresh_overwrites_existing_plain_text_resume():
    with tempfile.TemporaryDirectory() as tmp:
        data_folder = Path(tmp)
        (data_folder / "resume.pdf").write_bytes(b"%PDF-fake")
        plain_text_file = data_folder / "plain_text_resume.yaml"
        plain_text_file.write_text("stale: true\n", encoding="utf-8")

        parameters = {
            "dataFolder": data_folder,
            "plainTextResumeFile": plain_text_file,
        }

        with patch(
            "main.extract_plain_text_resume", return_value="fresh: true\n"
        ) as mock_extract:
            result = main.force_refresh_plain_text_resume(
                parameters, "sk-test"
            )

        mock_extract.assert_called_once()
        assert result == plain_text_file
        assert plain_text_file.read_text(encoding="utf-8") == "fresh: true\n"


def test_force_refresh_requires_resume_pdf():
    with tempfile.TemporaryDirectory() as tmp:
        data_folder = Path(tmp)
        parameters = {
            "dataFolder": data_folder,
            "plainTextResumeFile": data_folder / "plain_text_resume.yaml",
        }

        with pytest.raises(FileNotFoundError):
            main.force_refresh_plain_text_resume(parameters, "sk-test")
