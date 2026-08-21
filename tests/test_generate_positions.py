import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

import main


def test_generate_positions_returns_inferred_list():
    with tempfile.TemporaryDirectory() as tmp:
        data_folder = Path(tmp)
        (data_folder / "resume.pdf").write_bytes(b"%PDF-fake")
        parameters = {"dataFolder": data_folder}

        with patch(
            "main.infer_positions_from_resume",
            return_value=["Python разработчик", "Backend developer"],
        ) as mock_infer:
            result = main.generate_positions_from_resume(parameters, "sk-test")

        mock_infer.assert_called_once()
        assert result == ["Python разработчик", "Backend developer"]


def test_generate_positions_requires_resume_pdf():
    with tempfile.TemporaryDirectory() as tmp:
        parameters = {"dataFolder": Path(tmp)}

        with pytest.raises(FileNotFoundError):
            main.generate_positions_from_resume(parameters, "sk-test")


if __name__ == "__main__":
    test_generate_positions_returns_inferred_list()
    test_generate_positions_requires_resume_pdf()
    print("All tests passed.")
