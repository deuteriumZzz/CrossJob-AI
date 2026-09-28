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


def test_send_due_hh_reminders_sends_and_marks():
    """headhunter.auto_reminder: те же кандидаты, что due_hh_reminders()
    выбрал бы для ручной кнопки «Напомнить о себе» — отправляются сами,
    без подтверждения, и помечаются reminder_sent_at, чтобы не
    напомнить дважды (see due_hh_reminders())."""
    from datetime import datetime, timedelta

    now = datetime.now().astimezone()
    applied_log = MagicMock()
    applied_log.entries_by_source_and_status.return_value = [
        {
            "external_id": "1",
            "company": "Acme",
            "title": "Python разработчик",
            "applied_at": (now - timedelta(days=10)).isoformat(),
            "last_known_state": None,
            "reminder_sent_at": None,
        },
        {
            # Уже просмотрели — не молчание, напоминать не нужно.
            "external_id": "2",
            "company": "Seen",
            "title": "Dev",
            "applied_at": (now - timedelta(days=10)).isoformat(),
            "last_known_state": "Просмотрен",
            "reminder_sent_at": None,
        },
    ]
    parameters = {"headhunter": {"reminder_follow_up_days": 7}}
    with patch(
        "main.send_chat_cover_letter", return_value=True
    ) as send_mock, patch("main.notify_routine") as notify_mock:
        main._send_due_hh_reminders(parameters, MagicMock(), applied_log)
    send_mock.assert_called_once_with(ANY, "1", ANY)
    applied_log.mark_reminder_sent.assert_called_once_with("headhunter", "1")
    notify_mock.assert_called_once()


def test_send_due_hh_reminders_does_not_mark_on_failed_send():
    from datetime import datetime, timedelta

    now = datetime.now().astimezone()
    applied_log = MagicMock()
    applied_log.entries_by_source_and_status.return_value = [
        {
            "external_id": "1",
            "company": "Acme",
            "title": "Dev",
            "applied_at": (now - timedelta(days=10)).isoformat(),
            "last_known_state": None,
            "reminder_sent_at": None,
        }
    ]
    parameters = {"headhunter": {"reminder_follow_up_days": 7}}
    with patch("main.send_chat_cover_letter", return_value=False):
        main._send_due_hh_reminders(parameters, MagicMock(), applied_log)
    applied_log.mark_reminder_sent.assert_not_called()


if __name__ == "__main__":
    test_answer_headhunter_messages_retries_once_then_succeeds()
    test_answer_headhunter_messages_gives_up_after_second_failure()
    print("All tests passed.")
