"""A live Telegram gateway owns bot polling even during reconnects."""

from pathlib import Path

from filelock import Timeout as FileLockTimeout

import main
from src.job_sources.hr_replies import DraftStore
from src.job_sources.telegram_conversations import TelegramConversations


def _parameters(tmp_path: Path) -> dict:
    secrets_file = tmp_path / "secrets.yaml"
    secrets_file.write_text(
        "notifications:\n"
        "  telegram_bot_token: fake-token\n"
        "  telegram_chat_id: '123'\n",
        encoding="utf-8",
    )
    return {
        "secretsFile": secrets_file,
        "outputFileDirectory": tmp_path,
    }


def test_command_tick_skips_reconnecting_gateway(tmp_path, monkeypatch):
    """The source connection can be down while its bot poller is alive."""
    monkeypatch.setattr(main, "_maybe_send_daily_digest", lambda *a: None)
    monkeypatch.setattr(main, "active_watcher", lambda: None)
    monkeypatch.setattr(main, "gateway_state", lambda: {"alive": True})

    def unexpected_poll(*_args):
        raise AssertionError("scheduler must not start a second bot poll")

    monkeypatch.setattr(main, "poll_bot_updates", unexpected_poll)
    main.check_telegram_commands(_parameters(tmp_path), "")


def test_command_tick_skips_lock_contention(tmp_path, monkeypatch):
    """A second app process must leave the shared offset untouched."""
    offset_file = tmp_path / ".telegram_control_offset.json"
    offset_file.write_text('{"offset": 17}', encoding="utf-8")
    monkeypatch.setattr(main, "_maybe_send_daily_digest", lambda *a: None)
    monkeypatch.setattr(main, "active_watcher", lambda: None)
    monkeypatch.setattr(main, "gateway_state", lambda: {"alive": False})

    def locked(*_args):
        lock_path = tmp_path / ".telegram_control_offset.json.lock"
        raise FileLockTimeout(str(lock_path))

    monkeypatch.setattr(main, "poll_bot_updates", locked)
    warnings = []
    monkeypatch.setattr(main.logger, "warning", warnings.append)
    main.check_telegram_commands(_parameters(tmp_path), "")
    assert warnings == []
    assert offset_file.read_text(encoding="utf-8") == '{"offset": 17}'


def test_form_approval_poll_skips_reconnecting_gateway(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "active_watcher", lambda: None)
    monkeypatch.setattr(main, "gateway_state", lambda: {"alive": True})

    def unexpected_poll(*_args):
        raise AssertionError("form approval must not start a second poll")

    monkeypatch.setattr(main, "poll_bot_updates", unexpected_poll)
    warnings = []
    monkeypatch.setattr(main.logger, "warning", warnings.append)
    main._process_pending_form_approvals(_parameters(tmp_path), "")
    assert warnings == []


def test_form_approval_poll_skips_lock_contention(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "active_watcher", lambda: None)
    monkeypatch.setattr(main, "gateway_state", lambda: {"alive": False})

    def locked(*_args):
        raise FileLockTimeout("other bot poller")

    monkeypatch.setattr(main, "poll_bot_updates", locked)
    warnings = []
    monkeypatch.setattr(main.logger, "warning", warnings.append)
    main._process_pending_form_approvals(_parameters(tmp_path), "")
    assert warnings == []


def test_scheduled_send_skips_reconnecting_gateway(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "active_watcher", lambda: None)
    monkeypatch.setattr(main, "gateway_state", lambda: {"alive": True})

    def unexpected_queue(_folder):
        raise AssertionError("gateway owns scheduled sends during reconnect")

    monkeypatch.setattr(main, "pending_telegram_sends", unexpected_queue)
    main.flush_telegram_scheduled({"outputFileDirectory": tmp_path})


def test_reply_poll_skips_reconnecting_gateway(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "active_watcher", lambda: None)
    monkeypatch.setattr(main, "gateway_state", lambda: {"alive": True})
    monkeypatch.setattr(main, "flush_telegram_scheduled", lambda _p: None)
    main.check_telegram_replies({"outputFileDirectory": tmp_path}, "")


def test_bot_draft_reports_text_sent_if_resume_fails(tmp_path, monkeypatch):
    output_folder = tmp_path / "output"
    output_folder.mkdir()
    draft_store = DraftStore(output_folder / main.HR_DRAFTS_FILE)
    code = draft_store.add("hr_anna", "Привет", "first", "")
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1")
    monkeypatch.setattr(main, "telegram_resumes", lambda _path: [resume])
    secrets_file = tmp_path / "secrets.yaml"
    secrets_file.write_text(
        "telegram:\n  api_id: 1\n  api_hash: fake\n", encoding="utf-8"
    )

    class MessageClient:
        def __init__(self, *_args):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def send_message(self, _contact, _text):
            return None

    monkeypatch.setattr(main, "TelegramSourceClient", MessageClient)

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def send_file(self, *_args):
            raise OSError("файл не найден")

    monkeypatch.setattr(main, "_telegram_client", lambda _params: Client())
    replies = []
    monkeypatch.setattr(
        main,
        "bot_request",
        lambda _token, _method, payload: replies.append(payload),
    )
    main._handle_vacancy_button(
        {
            "outputFileDirectory": output_folder,
            "dataFolder": tmp_path,
            "secretsFile": secrets_file,
        },
        "",
        "bot-token",
        {
            "id": "callback",
            "data": f"d:{code}:0",
            "message": {"chat": {"id": 1}, "message_id": 2},
        },
    )
    assert "Текст отправлен" in replies[0]["text"]
    assert "резюме не ушло" in replies[0]["text"]
    assert draft_store.get(code) is None
    conversation_path = output_folder / "telegram_conversations.json"
    history = TelegramConversations(conversation_path).get("hr_anna")
    assert [msg["text"] for msg in history["messages"]] == ["Привет"]
