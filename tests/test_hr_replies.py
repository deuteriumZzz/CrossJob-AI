import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import main
from src.job import Job
from src.job_sources.applied_log import AppliedLog, effective_stage
from src.job_sources.hr_replies import (
    DraftStore,
    build_digest,
    due_follow_ups,
)
from src.job_sources.telegram_control import poll_control_commands
from src.job_sources.telegram_conversations import TelegramConversations


def _setup(tmp: str):
    data = Path(tmp) / "data"
    out = Path(tmp) / "output"
    data.mkdir()
    out.mkdir()
    secrets = data / "secrets.yaml"
    secrets.write_text(
        "telegram:\n  api_id: 1\n  api_hash: h\n", encoding="utf-8"
    )
    (data / main.RESUME_PDF).write_bytes(b"%PDF fake")
    params = {
        "dataFolder": data,
        "outputFileDirectory": out,
        "secretsFile": secrets,
    }
    log = AppliedLog(out / "applied_log.json")
    job = Job(
        role="Python Dev",
        company="Acme",
        link="https://t.me/jobs/1",
        source="telegram",
        external_id="1",
    )
    log.record(job, "", "", "applied", 8, [])
    conversations = TelegramConversations(out / "telegram_conversations.json")
    conversations.record_outbound("hr_anna", "Здравствуйте!", job.link)
    return params, log, conversations


def test_question_gets_draft_and_stage(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        params, log, conversations = _setup(tmp)
        sent: list[str] = []
        monkeypatch.setattr(main, "notify", lambda p, text: sent.append(text))
        monkeypatch.setattr(main, "classify_reply", lambda t, k: "question")
        monkeypatch.setattr(
            main, "generate_reply", lambda *a, **k: "От 250 000 ₽."
        )

        main._react_to_hr_reply(
            params, "key", conversations.get("hr_anna"), "Ваши ожидания?"
        )

        drafts = DraftStore(params["outputFileDirectory"] / main.HR_DRAFTS_FILE)
        [(code, draft)] = drafts.all().items()
        assert draft["contact"] == "hr_anna"
        assert draft["text"] == "От 250 000 ₽."
        assert f"отправить {code}" in sent[0]
        assert "Acme — Python Dev" in sent[0]
        entry = log.find_by_source_and_external_id("telegram", "1")
        assert effective_stage(entry) == "replied"
        reloaded = TelegramConversations(conversations.path)
        assert reloaded.get("hr_anna")["label"] == "question"


def test_interest_marks_interview_without_draft(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        params, log, conversations = _setup(tmp)
        sent: list[str] = []
        monkeypatch.setattr(main, "notify", lambda p, text: sent.append(text))
        monkeypatch.setattr(main, "classify_reply", lambda t, k: "interest")

        main._react_to_hr_reply(
            params, "key", conversations.get("hr_anna"), "Созвонимся завтра?"
        )

        entry = log.find_by_source_and_external_id("telegram", "1")
        assert effective_stage(entry) == "interview"
        assert sent and sent[0].startswith("🟢")
        assert not DraftStore(
            params["outputFileDirectory"] / main.HR_DRAFTS_FILE
        ).all()


def test_send_hr_draft_sends_and_records(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        params, _, conversations = _setup(tmp)
        drafts = DraftStore(params["outputFileDirectory"] / main.HR_DRAFTS_FILE)
        code = drafts.add("hr_anna", "Черновик", "reply", "")
        delivered: list[tuple] = []

        class _Client:
            def __init__(self, *a):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *e):
                return False

            def send_message(self, contact, text):
                delivered.append((contact, text))

        monkeypatch.setattr(main, "TelegramSourceClient", _Client)

        result = main.send_hr_draft(params, code, "Исправленный текст")

        assert result == "Отправлено @hr_anna."
        assert delivered == [("hr_anna", "Исправленный текст")]
        assert drafts.all() == {}
        reloaded = TelegramConversations(conversations.path)
        assert reloaded.get("hr_anna")["messages"][-1]["text"] == (
            "Исправленный текст"
        )
        assert "не найден" in main.send_hr_draft(params, code)


def test_new_draft_for_same_contact_replaces_old():
    with tempfile.TemporaryDirectory() as tmp:
        drafts = DraftStore(Path(tmp) / "d.json")
        drafts.add("hr_anna", "первый", "reply", "")
        code = drafts.add("hr_anna", "второй", "reply", "")
        assert list(drafts.all()) == [code]


def test_due_follow_ups():
    now = datetime(2030, 1, 10, tzinfo=timezone.utc)
    old = (now - timedelta(days=8)).isoformat()
    fresh = (now - timedelta(days=2)).isoformat()
    convs = [
        {"contact": "silent", "messages": [{"direction": "out", "at": old}]},
        {"contact": "fresh", "messages": [{"direction": "out", "at": fresh}]},
        {
            "contact": "answered",
            "messages": [
                {"direction": "out", "at": old},
                {"direction": "in", "at": old},
            ],
        },
        {
            "contact": "done",
            "followed_up": True,
            "messages": [{"direction": "out", "at": old}],
        },
    ]
    assert [c["contact"] for c in due_follow_ups(convs, 7, now)] == ["silent"]
    assert due_follow_ups(convs, 0, now) == []


def test_digest_counts_last_day():
    with tempfile.TemporaryDirectory() as tmp:
        log = AppliedLog(Path(tmp) / "applied_log.json")
        job = Job(role="Dev", company="Co", source="headhunter", external_id="1")
        log.record(job, "", "", "applied", 8, [])
        log.update_reply_state("headhunter", "1", "Приглашение на интервью")
        text = build_digest(log, [], {"ab12": {}})
        assert "Откликов: 1" in text
        assert "интервью: 1" in text
        assert "🟢 Co — Dev" in text
        assert "Ждут вашего подтверждения: 1" in text


def test_daily_digest_sent_once_per_day(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        sent: list[str] = []
        monkeypatch.setattr(
            main, "send_notification", lambda t, c, text: sent.append(text)
        )
        params = {"outputFileDirectory": out, "digest": {"hour": 0}}
        main._maybe_send_daily_digest(params, "t", "c")
        main._maybe_send_daily_digest(params, "t", "c")
        assert len(sent) == 1
        state = json.loads((out / ".digest_state.json").read_text())
        assert state["last_sent"] == datetime.now().astimezone().date().isoformat()
        main._maybe_send_daily_digest(
            {"outputFileDirectory": Path(tmp) / "x", "digest": {"enabled": False}},
            "t",
            "c",
        )
        assert len(sent) == 1


def test_control_commands_parse_draft_actions(monkeypatch):
    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "result": [
                    {"update_id": 1, "message": {"chat": {"id": 5}, "text": "отправить AB12"}},
                    {"update_id": 2, "message": {"chat": {"id": 5}, "text": "skip cd34"}},
                ]
            }

    import src.job_sources.telegram_control as tc

    monkeypatch.setattr(tc.httpx, "get", lambda *a, **k: _Resp())
    with tempfile.TemporaryDirectory() as tmp:
        commands = poll_control_commands("t", "5", Path(tmp))
    assert commands == [
        {"action": "send_draft", "code": "ab12"},
        {"action": "skip_draft", "code": "cd34"},
    ]
