import tempfile
from pathlib import Path
from unittest.mock import ANY, MagicMock, patch

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


def test_send_missing_cover_letters_skips_already_sent_and_empty():
    applied_log = MagicMock()
    applied_log.entries_by_source_and_status.return_value = [
        {
            "external_id": "1",
            "company": "Acme",
            "title": "Dev",
            "cover_letter": "Hello Acme",
            "cover_letter_sent_via_chat": False,
        },
        {
            "external_id": "2",
            "company": "NoLetter",
            "title": "Dev",
            "cover_letter": "",
            "cover_letter_sent_via_chat": False,
        },
        {
            "external_id": "3",
            "company": "AlreadySent",
            "title": "Dev",
            "cover_letter": "Hi",
            "cover_letter_sent_via_chat": True,
        },
    ]
    with patch("main.send_chat_cover_letter", return_value=True) as send_mock:
        main._send_missing_cover_letters(MagicMock(), applied_log)
    send_mock.assert_called_once_with(ANY, "1", "Hello Acme")
    applied_log.mark_cover_letter_sent_via_chat.assert_called_once_with(
        "headhunter", "1"
    )


def test_send_missing_cover_letters_does_not_mark_on_failed_send():
    applied_log = MagicMock()
    applied_log.entries_by_source_and_status.return_value = [
        {
            "external_id": "1",
            "company": "Acme",
            "title": "Dev",
            "cover_letter": "Hello Acme",
            "cover_letter_sent_via_chat": False,
        }
    ]
    with patch("main.send_chat_cover_letter", return_value=False):
        main._send_missing_cover_letters(MagicMock(), applied_log)
    applied_log.mark_cover_letter_sent_via_chat.assert_not_called()


if __name__ == "__main__":
    test_answer_headhunter_messages_retries_once_then_succeeds()
    test_answer_headhunter_messages_gives_up_after_second_failure()
    print("All tests passed.")
