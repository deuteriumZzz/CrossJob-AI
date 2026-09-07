import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import main
from src.utils.constants import RESUME_PDF


def _parameters(data_folder: Path) -> dict:
    (data_folder / RESUME_PDF).write_bytes(b"%PDF-fake")
    secrets_file = data_folder / "secrets.yaml"
    secrets_file.write_text("llm_api_key: 'sk-test'\n", encoding="utf-8")
    return {
        "dataFolder": data_folder,
        "secretsFile": secrets_file,
        "headhunter": {"auto_reply": True},
    }


def test_answer_headhunter_messages_retries_once_then_succeeds():
    with tempfile.TemporaryDirectory() as tmp:
        parameters = _parameters(Path(tmp))
        applied_log = MagicMock()
        with patch(
            "main.fetch_new_employer_messages",
            side_effect=[
                Exception("Timed out receiving message from renderer"),
                [],
            ],
        ) as fetch_mock, patch("main.time.sleep"):
            main._answer_headhunter_messages(
                parameters, MagicMock(), applied_log, "sk-test"
            )
        assert fetch_mock.call_count == 2


def test_answer_headhunter_messages_gives_up_after_second_failure():
    with tempfile.TemporaryDirectory() as tmp:
        parameters = _parameters(Path(tmp))
        applied_log = MagicMock()
        with patch(
            "main.fetch_new_employer_messages",
            side_effect=[Exception("first"), Exception("second")],
        ) as fetch_mock, patch("main.time.sleep"):
            main._answer_headhunter_messages(
                parameters, MagicMock(), applied_log, "sk-test"
            )
        assert fetch_mock.call_count == 2


if __name__ == "__main__":
    test_answer_headhunter_messages_retries_once_then_succeeds()
    test_answer_headhunter_messages_gives_up_after_second_failure()
    print("All tests passed.")
