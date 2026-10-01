import json
import tempfile
from pathlib import Path
from unittest.mock import ANY, MagicMock, patch

import pytest

import main
from src.job_sources.headhunter.browser_replies import ChatSendResult
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


def test_send_headhunter_reminders_reuses_one_browser_for_the_batch():
    """Массовая отправка не должна перезапускать Chrome на каждый чат."""
    with tempfile.TemporaryDirectory() as tmp:
        output_folder = Path(tmp)
        parameters = {"outputFileDirectory": output_folder}
        driver = MagicMock()
        applied_log = MagicMock()
        reminders = [
            {"external_id": "1", "text": "Первое напоминание"},
            {"external_id": "2", "text": "Второе напоминание"},
        ]
        with patch(
            "main.init_browser", return_value=driver
        ) as init_mock, patch(
            "main.AppliedLog", return_value=applied_log
        ), patch(
            "main.send_chat_cover_letter_result",
            side_effect=[
                ChatSendResult(sent=True),
                ChatSendResult(sent=False),
            ],
        ) as send_mock:
            results = main.send_headhunter_reminders(parameters, reminders)

    init_mock.assert_called_once_with(
        output_folder / ".chrome_profile_headhunter"
    )
    assert send_mock.call_count == 2
    driver.quit.assert_called_once()
    applied_log.mark_reminder_sent.assert_called_once_with("headhunter", "1")
    assert results == [
        {"external_id": "1", "sent": True},
        {"external_id": "2", "sent": False},
    ]


def test_send_headhunter_reminders_passes_stored_vacancy_link_to_chat_sender():
    with tempfile.TemporaryDirectory() as tmp:
        output_folder = Path(tmp)
        parameters = {"outputFileDirectory": output_folder}
        driver = MagicMock()
        applied_log = MagicMock()
        applied_log.find_by_source_and_external_id.return_value = {
            "link": "https://hh.ru/vacancy/1"
        }
        reminder = {"external_id": "1", "text": "Напоминание"}
        with patch("main.init_browser", return_value=driver), patch(
            "main.AppliedLog", return_value=applied_log
        ), patch(
            "main.send_chat_cover_letter_result",
            return_value=ChatSendResult(sent=True),
        ) as send_mock:
            main.send_headhunter_reminders(parameters, [reminder])

    send_mock.assert_called_once_with(
        driver, "1", "Напоминание", "https://hh.ru/vacancy/1"
    )


def test_stored_hh_vacancy_url_accepts_regional_hh_subdomain():
    applied_log = MagicMock()
    applied_log.find_by_source_and_external_id.return_value = {
        "link": "https://spb.hh.ru/vacancy/1"
    }

    assert main._stored_hh_vacancy_url(applied_log, "1") == (
        "https://spb.hh.ru/vacancy/1"
    )


def test_send_headhunter_reminders_marks_archived_vacancy_and_does_not_send():
    with tempfile.TemporaryDirectory() as tmp:
        output_folder = Path(tmp)
        parameters = {"outputFileDirectory": output_folder}
        driver = MagicMock()
        applied_log = MagicMock()
        applied_log.find_by_source_and_external_id.return_value = {
            "link": "https://hh.ru/vacancy/1"
        }
        with patch("main.init_browser", return_value=driver), patch(
            "main.AppliedLog", return_value=applied_log
        ), patch(
            "main.send_chat_cover_letter_result",
            return_value=ChatSendResult(sent=False, archived=True),
        ):
            results = main.send_headhunter_reminders(
                parameters, [{"external_id": "1", "text": "Напоминание"}]
            )

    assert results == [
        {
            "external_id": "1",
            "sent": False,
            "error": "Вакансия в архиве",
        }
    ]
    applied_log.update_reply_state.assert_called_once_with(
        "headhunter", "1", "Вакансия в архиве"
    )
    applied_log.mark_reminder_sent.assert_not_called()


def test_send_headhunter_reminders_marks_authorization_unavailable_vacancy():
    with tempfile.TemporaryDirectory() as tmp:
        output_folder = Path(tmp)
        parameters = {"outputFileDirectory": output_folder}
        driver = MagicMock()
        applied_log = MagicMock()
        applied_log.find_by_source_and_external_id.return_value = {
            "link": "https://hh.ru/vacancy/1"
        }
        with patch("main.init_browser", return_value=driver), patch(
            "main.AppliedLog", return_value=applied_log
        ), patch(
            "main.send_chat_cover_letter_result",
            return_value=ChatSendResult(sent=False, unavailable=True),
        ):
            results = main.send_headhunter_reminders(
                parameters, [{"external_id": "1", "text": "Напоминание"}]
            )

    assert results == [
        {
            "external_id": "1",
            "sent": False,
            "error": "Вакансия недоступна для текущего аккаунта",
        }
    ]
    applied_log.update_reply_state.assert_called_once_with(
        "headhunter", "1", "Вакансия недоступна для текущего аккаунта"
    )
    applied_log.mark_reminder_sent.assert_not_called()


def test_send_headhunter_reminders_continues_after_one_chat_errors():
    with tempfile.TemporaryDirectory() as tmp:
        output_folder = Path(tmp)
        parameters = {"outputFileDirectory": output_folder}
        driver = MagicMock()
        applied_log = MagicMock()
        reminders = [
            {"external_id": "1", "text": "Первое напоминание"},
            {"external_id": "2", "text": "Второе напоминание"},
        ]
        with patch("main.init_browser", return_value=driver), patch(
            "main.AppliedLog", return_value=applied_log
        ), patch(
            "main.send_chat_cover_letter_result",
            side_effect=[
                RuntimeError("HH недоступен"),
                ChatSendResult(sent=True),
            ],
        ) as send_mock:
            results = main.send_headhunter_reminders(parameters, reminders)

    assert send_mock.call_count == 2
    driver.quit.assert_called_once()
    applied_log.mark_reminder_sent.assert_called_once_with("headhunter", "2")
    assert results == [
        {
            "external_id": "1",
            "sent": False,
            "error": "Не удалось открыть чат на HH",
        },
        {"external_id": "2", "sent": True},
    ]


def test_send_hh_reminders_returns_failures_when_browser_cannot_start():
    """Сбой запуска Chrome не должен обрывать HTTP-запрос и UI."""
    with tempfile.TemporaryDirectory() as tmp:
        output_folder = Path(tmp)
        parameters = {"outputFileDirectory": output_folder}
        reminders = [
            {"external_id": "1", "text": "Первое напоминание"},
            {"external_id": "2", "text": "Второе напоминание"},
        ]
        with patch(
            "main.init_browser",
            side_effect=RuntimeError("Chrome profile is busy"),
        ):
            results = main.send_headhunter_reminders(parameters, reminders)

    assert results == [
        {
            "external_id": "1",
            "sent": False,
            "error": "Не удалось запустить браузер HH",
        },
        {
            "external_id": "2",
            "sent": False,
            "error": "Не удалось запустить браузер HH",
        },
    ]


def test_send_headhunter_reminders_does_not_start_second_hh_session():
    """Повторный клик во время отправки не должен трогать профиль Chrome."""
    with tempfile.TemporaryDirectory() as tmp:
        parameters = {"outputFileDirectory": Path(tmp)}
        reminders = [{"external_id": "1", "text": "Напоминание"}]
        main._HEADHUNTER_BROWSER_SESSION_LOCK.acquire()
        try:
            with patch("main.init_browser") as init_mock:
                results = main.send_headhunter_reminders(parameters, reminders)
        finally:
            main._HEADHUNTER_BROWSER_SESSION_LOCK.release()

    init_mock.assert_not_called()
    assert results == [
        {
            "external_id": "1",
            "sent": False,
            "error": "Сессия HH уже выполняет другую операцию",
        }
    ]


def test_scheduled_hh_check_skips_when_manual_session_is_active():
    main._HEADHUNTER_BROWSER_SESSION_LOCK.acquire()
    try:
        with patch(
            "main._check_headhunter_replies_with_session"
        ) as check_mock:
            main.check_headhunter_replies({}, "sk-test")
    finally:
        main._HEADHUNTER_BROWSER_SESSION_LOCK.release()

    check_mock.assert_not_called()


def test_hh_cleanup_does_not_start_browser_while_session_is_busy():
    with tempfile.TemporaryDirectory() as tmp:
        parameters = {
            "outputFileDirectory": Path(tmp),
            "headhunter": {"auto_cleanup_negotiations": True},
        }
        main._HEADHUNTER_BROWSER_SESSION_LOCK.acquire()
        try:
            with patch("main.init_browser") as init_mock:
                main.cleanup_headhunter_negotiations(parameters)
        finally:
            main._HEADHUNTER_BROWSER_SESSION_LOCK.release()

    init_mock.assert_not_called()


def test_hh_employer_block_does_not_start_browser_while_session_is_busy():
    with tempfile.TemporaryDirectory() as tmp:
        output_folder = Path(tmp)
        (output_folder / "applied_log.json").write_text(
            json.dumps(
                {
                    "applications": [
                        {
                            "source": "headhunter",
                            "company": "Acme",
                            "title": "Developer",
                            "link": "https://hh.ru/vacancy/1",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        main._HEADHUNTER_BROWSER_SESSION_LOCK.acquire()
        try:
            with patch("main.init_browser") as init_mock:
                assert (
                    main.block_headhunter_employer(
                        {"outputFileDirectory": output_folder}, "Acme"
                    )
                    is False
                )
        finally:
            main._HEADHUNTER_BROWSER_SESSION_LOCK.release()

    init_mock.assert_not_called()


def test_hh_search_skips_when_manual_session_is_active():
    main._HEADHUNTER_BROWSER_SESSION_LOCK.acquire()
    try:
        with patch(
            "main._search_and_apply_headhunter_with_session"
        ) as search_mock:
            main.search_and_apply_headhunter({}, "sk-test")
    finally:
        main._HEADHUNTER_BROWSER_SESSION_LOCK.release()

    search_mock.assert_not_called()


def test_send_headhunter_reminders_ignores_browser_close_failure():
    """Ответ об отправке не теряется, если Chrome уже завершился сам."""
    with tempfile.TemporaryDirectory() as tmp:
        output_folder = Path(tmp)
        parameters = {"outputFileDirectory": output_folder}
        driver = MagicMock()
        driver.quit.side_effect = RuntimeError("invalid session id")
        applied_log = MagicMock()
        reminders = [{"external_id": "1", "text": "Напоминание"}]
        with patch("main.init_browser", return_value=driver), patch(
            "main.AppliedLog", return_value=applied_log
        ), patch(
            "main.send_chat_cover_letter_result",
            return_value=ChatSendResult(sent=False),
        ):
            results = main.send_headhunter_reminders(parameters, reminders)

    assert results == [{"external_id": "1", "sent": False}]


def test_send_headhunter_reminders_closes_browser_after_unexpected_error():
    """Исключение записи в журнал не должно оставлять профиль HH занятым."""
    with tempfile.TemporaryDirectory() as tmp:
        output_folder = Path(tmp)
        parameters = {"outputFileDirectory": output_folder}
        driver = MagicMock()
        applied_log = MagicMock()
        applied_log.mark_reminder_sent.side_effect = RuntimeError("disk error")
        with patch("main.init_browser", return_value=driver), patch(
            "main.AppliedLog", return_value=applied_log
        ), patch(
            "main.send_chat_cover_letter_result",
            return_value=ChatSendResult(sent=True),
        ), pytest.raises(
            RuntimeError, match="disk error"
        ):
            main.send_headhunter_reminders(
                parameters, [{"external_id": "1", "text": "Напоминание"}]
            )

    driver.quit.assert_called_once()


if __name__ == "__main__":
    test_answer_headhunter_messages_retries_once_then_succeeds()
    test_answer_headhunter_messages_gives_up_after_second_failure()
    print("All tests passed.")
