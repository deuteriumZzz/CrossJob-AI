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
from tests.test_webui_api import client  # noqa: F401  (fixture)


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

        drafts = DraftStore(
            params["outputFileDirectory"] / main.HR_DRAFTS_FILE
        )
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
        drafts = DraftStore(
            params["outputFileDirectory"] / main.HR_DRAFTS_FILE
        )
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
        job = Job(
            role="Dev", company="Co", source="headhunter", external_id="1"
        )
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
        assert (
            state["last_sent"]
            == datetime.now().astimezone().date().isoformat()
        )
        main._maybe_send_daily_digest(
            {
                "outputFileDirectory": Path(tmp) / "x",
                "digest": {"enabled": False},
            },
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
                    {
                        "update_id": 1,
                        "message": {
                            "chat": {"id": 5},
                            "text": "отправить AB12",
                        },
                    },
                    {
                        "update_id": 2,
                        "message": {"chat": {"id": 5}, "text": "skip cd34"},
                    },
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


def test_outreach_settings_roundtrip(client):  # noqa: F811
    from src.webui import api as webapi

    s = client.get("/api/settings/outreach").json()
    assert s["email_connected"] is False
    assert s["skip_us_only"] is True  # по умолчанию US-only отсекается
    assert s["follow_up_days"] == 7

    s = client.post(
        "/api/settings/outreach",
        json={
            "email_address": "me@gmail.com",
            "email_app_password": "abcd efgh ijkl mnop",
            "hunter_api_key": "hunter-key-123456",
            "follow_up_days": 5,
            "digest_hour": 8,
            "skip_us_only": False,
            "skip_europe_only": True,
        },
    ).json()
    assert s["email_connected"] is True
    assert s["follow_up_days"] == 5
    assert s["digest_hour"] == 8
    assert (s["skip_us_only"], s["skip_europe_only"]) == (False, True)
    assert s["hunter_preview"] == "hunt…3456"

    ctx = webapi.get_ctx()
    secrets = main.ConfigValidator.load_yaml(ctx.secrets_file)
    assert secrets["email"]["app_password"] == "abcdefghijklmnop"
    assert ctx.config["direct"]["follow_up_days"] == 5
    assert ctx.config["excluded_remote_regions"] == ["europe_only"]
    assert "abcdefgh" not in str(client.get("/api/settings/outreach").json())


def test_hr_drafts_queue_endpoint(client):  # noqa: F811
    from src.webui import api as webapi

    ctx = webapi.get_ctx()
    ctx.applied_log.record(
        Job(
            role="Dev",
            company="Acme",
            link="https://t.me/jobs/9",
            source="telegram",
            external_id="9",
        ),
        "",
        "",
        "applied",
        8,
        [],
    )
    drafts = DraftStore(ctx.output_folder / main.HR_DRAFTS_FILE)
    drafts.add("hr_anna", "Ответ", "reply", "https://t.me/jobs/9")
    drafts.add(
        "hr@acme.io", "Письмо", "email", "https://t.me/jobs/9", channel="email"
    )
    items = client.get("/api/hr-drafts").json()
    assert {(i["channel"], i["company"]) for i in items} == {
        ("telegram", "Acme"),
        ("email", "Acme"),
    }
    names = [
        c["name"] for c in client.get("/api/status").json()["chat_checks"]
    ]
    assert (
        "check_email_replies" in names and "check_telegram_commands" in names
    )


def test_company_email_language_by_domain_and_text():
    """Русское письмо — компаниям из России/СНГ, даже с латинским
    названием (домен .ru/.kz/.by, текст вакансии по-русски); остальным —
    английское."""
    from src.job_sources.hr_replies import _cis_company, _looks_russian

    assert _cis_company({"website": "https://kaspi.kz/", "contacts": []})
    assert _cis_company(
        {"website": "", "contacts": [{"kind": "email", "value": "hr@ozon.ru"}]}
    )
    assert not _cis_company(
        {
            "website": "nvidia.com",
            "contacts": [{"kind": "email", "value": "hr@nvidia.com"}],
        }
    )
    assert _looks_russian("Ищем Python-разработчика в команду")


def test_build_contact_footer_prefers_resume_over_manual_override():
    """Резюме — источник по умолчанию; поле в настройках побеждает,
    только когда явно заполнено; пусто и там, и там — просто нет в
    подписи, ничего не выдумывается (без телефона в резюме и без
    ручного WhatsApp — WhatsApp не попадает в подпись)."""
    from src.job_sources.hr_replies import build_contact_footer

    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp)
        secrets = data / "secrets.yaml"
        secrets.write_text(
            "email:\n  address: me@gmail.com\n"
            "github:\n  username: deuteriumZzz\n",
            encoding="utf-8",
        )
        resume_yaml = data / "plain_text_resume.yaml"
        resume_yaml.write_text(
            "personal_information:\n"
            "  linkedin: linkedin.com/in/dmitry\n",
            encoding="utf-8",
        )
        params = {
            "secretsFile": secrets,
            "plainTextResumeFile": resume_yaml,
            "dataFolder": data,
            "direct": {"candidate_linkedin": "linkedin.com/in/override"},
        }
        footer = build_contact_footer(params, data / "resume.pdf")
        assert "me@gmail.com" in footer
        assert "github.com/deuteriumZzz" in footer
        # Ручное поле явно заполнено — побеждает над резюме.
        assert "linkedin.com/in/override" in footer
        assert "linkedin.com/in/dmitry" not in footer
        # Нет WhatsApp ни в резюме, ни в настройках — не выдумываем.
        assert "WhatsApp" not in footer


def test_due_hh_reminders_skips_viewed_and_already_reminded():
    from src.job_sources.hr_replies import due_hh_reminders, hh_reminder_text

    now = datetime.now(timezone.utc)
    old = (now - timedelta(days=10)).isoformat()
    recent = (now - timedelta(days=1)).isoformat()
    entries = [
        {  # молчат достаточно долго — кандидат
            "external_id": "1",
            "title": "Python разработчик",
            "applied_at": old,
            "last_known_state": None,
        },
        {  # ещё рано — только день прошёл
            "external_id": "2",
            "title": "Backend Dev",
            "applied_at": recent,
            "last_known_state": None,
        },
        {  # уже просмотрели — не молчание
            "external_id": "3",
            "title": "Dev",
            "applied_at": old,
            "last_known_state": "Просмотрен",
        },
        {  # уже напоминали — не повторяем
            "external_id": "4",
            "title": "Dev",
            "applied_at": old,
            "last_known_state": None,
            "reminder_sent_at": old,
        },
    ]
    due = due_hh_reminders(entries, days=7, now=now)
    assert [e["external_id"] for e in due] == ["1"]
    assert "Python разработчик" in hh_reminder_text(due[0])

    assert due_hh_reminders(entries, days=0, now=now) == []


def test_greeting_time_phrase_follows_moscow_hour():
    from zoneinfo import ZoneInfo

    from src.job_sources.hr_replies import greeting_time_phrase

    tz = ZoneInfo("Europe/Moscow")
    assert greeting_time_phrase(datetime(2026, 1, 1, 8, 0, tzinfo=tz)) == "доброе утро"
    assert greeting_time_phrase(datetime(2026, 1, 1, 14, 0, tzinfo=tz)) == "добрый день"
    assert greeting_time_phrase(datetime(2026, 1, 1, 20, 0, tzinfo=tz)) == "добрый вечер"
    assert greeting_time_phrase(datetime(2026, 1, 1, 3, 0, tzinfo=tz)) == ""
    # UTC-момент, который в Москве уже день (+3ч: 11:30 -> 14:30) —
    # считается по Москве, а не по UTC/локальному времени сервера.
    assert (
        greeting_time_phrase(
            datetime(2026, 1, 1, 11, 30, tzinfo=ZoneInfo("UTC"))
        )
        == "добрый день"
    )


def test_fit_telegram_length_cuts_at_sentence_boundary():
    from src.job_sources.hr_replies import (
        _TELEGRAM_MESSAGE_LIMIT,
        _fit_telegram_length,
    )

    short = "Здравствуйте! Интересует вакансия."
    assert _fit_telegram_length(short) == short

    long_text = (
        "Здравствуйте! Заинтересовала ваша вакансия Python-разработчика. "
        "У меня два года опыта с Django и FastAPI, строил CRM с нуля. "
        "Буду рад обсудить детали, если позиция ещё открыта, спасибо за внимание."
    )
    fitted = _fit_telegram_length(long_text)
    assert len(fitted) <= _TELEGRAM_MESSAGE_LIMIT
    assert fitted.endswith((".", "!", "?"))
