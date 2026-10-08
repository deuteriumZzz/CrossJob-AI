"""Доработки бэкенда под новый интерфейс (docs/UI_MAP.md, раздел 11):
каждая — добавка, старые данные и поведение по умолчанию не меняются."""

from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from src.webui import api
from tests.test_webui_api import client  # noqa: F401  (fixture)

# --- Уведомления: что присылать и история в приложении -------------------


def _params(tmp_path: Path, **extra) -> dict:
    secrets = tmp_path / "secrets.yaml"
    secrets.write_text(
        "notifications:\n"
        "  telegram_bot_token: 't'\n"
        "  telegram_chat_id: '1'\n",
        encoding="utf-8",
    )
    return {"secretsFile": secrets, "outputFileDirectory": tmp_path, **extra}


def test_notification_kind_by_category_and_text():
    from src.job_sources.telegram_notify import notification_kind

    assert notification_kind("HH: капча, нужен вход", "headhunter") == (
        "failure"
    )
    assert notification_kind("Откликнулся на 3 вакансии", "headhunter") == (
        "activity"
    )
    # Текст HR может содержать что угодно — тема решает.
    assert notification_kind("Ошибка в резюме?", "Ответы HR") == "activity"
    assert notification_kind("Осталось 1 ГБ", "Система") == "failure"


def test_muted_kind_is_not_sent_but_kept_in_history(tmp_path):
    from src.job_sources.telegram_notify import (
        notification_history,
        notify_from_secrets,
    )

    params = _params(tmp_path, notify={"failures": False})
    with patch(
        "src.job_sources.telegram_notify.send_notification"
    ) as send, patch(
        "src.job_sources.telegram_notify.get_or_create_topic",
        return_value=None,
    ):
        notify_from_secrets(params, "LinkedIn: капча", "linkedin")
        notify_from_secrets(params, "Откликнулся: Nova Tech", "linkedin")
    assert [c.args[2] for c in send.call_args_list] == [
        "Откликнулся: Nova Tech"
    ]
    history = notification_history(tmp_path)
    assert [(h["text"], h["status"]) for h in history] == [
        ("Откликнулся: Nova Tech", "sent"),
        ("LinkedIn: капча", "muted"),
    ]


def test_history_without_bot_marks_app_only(tmp_path):
    from src.job_sources.telegram_notify import (
        notification_history,
        notify_from_secrets,
    )

    secrets = tmp_path / "secrets.yaml"
    secrets.write_text("llm_api_key: 'x'\n", encoding="utf-8")
    notify_from_secrets(
        {"secretsFile": secrets, "outputFileDirectory": tmp_path},
        "Ответ HR @anna: добрый день",
        "Ответы HR",
    )
    (item,) = notification_history(tmp_path)
    assert item["status"] == "app" and item["kind"] == "activity"


def test_outreach_settings_notify_kinds_round_trip(client):  # noqa: F811
    body = client.get("/api/settings/outreach").json()
    assert body["notify_activity"] is True
    assert body["notify_failures"] is True
    response = client.post(
        "/api/settings/outreach", json={"notify_failures": False}
    )
    assert response.status_code == 200
    assert response.json()["notify_failures"] is False
    assert response.json()["notify_activity"] is True
    assert api.get_ctx().config["notify"]["failures"] is False


def test_notifications_endpoint_lists_newest_first(client):  # noqa: F811
    from src.job_sources.telegram_notify import record_notification

    params = {"outputFileDirectory": api.get_ctx().output_folder}
    record_notification(params, "первое", "headhunter", "activity", "sent")
    record_notification(params, "второе", "Система", "failure", "app")
    items = client.get("/api/notifications").json()["items"]
    assert [i["text"] for i in items] == ["второе", "первое"]


# --- Резервные копии: «Сделать копию сейчас» -----------------------------


def test_backup_now_creates_manual_copy_and_lists_it(client):  # noqa: F811
    out = api.get_ctx().output_folder
    (out / "applied_log.json").write_text(
        '{"applications": []}', encoding="utf-8"
    )
    response = client.post("/api/backups/now")
    assert response.status_code == 200
    body = response.json()
    manual = [b for b in body["backups"] if b["manual"]]
    assert [b["date"] for b in manual] == [body["date"]]
    assert (
        out.parent / "backups" / body["date"] / "applied_log.json"
    ).exists()


def test_backup_now_without_data_says_so(client):  # noqa: F811
    response = client.post("/api/backups/now")
    assert response.status_code == 409


def test_manual_backups_do_not_push_out_daily_ones(tmp_path):
    from datetime import date

    from src.utils.backup import KEEP_MANUAL, backup_now, daily_backup

    out = tmp_path / "output"
    out.mkdir()
    (out / "contact_book.json").write_text("{}", encoding="utf-8")
    daily_backup(out, date(2026, 10, 1))
    for i in range(KEEP_MANUAL + 3):
        backup_now(out, datetime(2026, 10, 2, 10, 0, i))
    daily_backup(out, date(2026, 10, 3))
    names = sorted(p.name for p in (tmp_path / "backups").iterdir())
    assert "2026-10-01" in names and "2026-10-03" in names
    assert len([n for n in names if len(n) > 10]) == KEEP_MANUAL


def test_restore_rejects_paths_outside_backups(client):  # noqa: F811
    response = client.post("/api/backups/restore", json={"date": "../output"})
    assert response.status_code == 400


# --- ИИ: порядок запасных провайдеров ------------------------------------


def test_llm_fallback_order_round_trip(client):  # noqa: F811
    assert client.get("/api/settings/llm").json()["fallback_order"] == []
    response = client.post(
        "/api/settings/llm", json={"fallback_order": ["groq", "gemini"]}
    )
    assert response.status_code == 200
    assert response.json()["fallback_order"] == ["groq", "gemini"]
    bad = client.post("/api/settings/llm", json={"fallback_order": ["nope"]})
    assert bad.status_code == 400


def test_fallback_order_puts_named_providers_first():
    from src.job_sources import llm_provider

    keys = {"openai": "a", "groq": "b", "gemini": "c", "mistral": "d"}
    built: list[str] = []

    def fake_build(provider, *args, **kwargs):
        built.append(provider)
        raise RuntimeError("не нужно строить")

    llm_provider.set_fallback_keys(keys)
    llm_provider.set_fallback_order(["mistral", "groq"])
    try:
        with patch.object(llm_provider, "_build_llm", side_effect=fake_build):
            llm_provider._build_fallback_llms("openai", 0)
    finally:
        llm_provider.set_fallback_keys({})
        llm_provider.set_fallback_order([])
    order = list(dict.fromkeys(built))
    assert order[:2] == ["mistral", "groq"]
    assert set(order) == {"mistral", "groq", "gemini"}


# --- Почта: свои правила письма ------------------------------------------


def test_letter_instructions_round_trip(client):  # noqa: F811
    text = "Пиши на «ты».\nУпомяни: готов к релокации"
    response = client.post(
        "/api/settings/outreach", json={"letter_instructions": text}
    )
    assert response.status_code == 200
    assert response.json()["letter_instructions"] == text
    assert api.get_ctx().config["direct"]["letter_instructions"] == text


# --- «Пауза на всё» -------------------------------------------------------


def test_pause_all_keeps_only_incoming_checks(tmp_path):
    from src.scheduler import Scheduler
    from src.utils.pause_all import set_paused

    noop = lambda p, k: None  # noqa: E731
    scheduler = Scheduler(
        source_map={
            "headhunter": noop,
            "check_hh_replies": noop,
            "check_telegram_commands": noop,
            "check_email_replies": noop,
        },
        parameters={"headhunter": {"schedule_enabled": True}},
        llm_api_key="key",
        output_folder=tmp_path,
        now_fn=lambda: datetime(2026, 10, 8, 10, 0),
    )
    assert "headhunter" in scheduler.due_sources()
    set_paused(tmp_path, True)
    assert sorted(scheduler.due_sources()) == [
        "check_email_replies",
        "check_telegram_commands",
    ]
    set_paused(tmp_path, False)
    assert "headhunter" in scheduler.due_sources()


def test_pause_all_api_round_trip(client):  # noqa: F811
    assert client.get("/api/status").json()["pause_all"]["paused"] is False
    response = client.post("/api/pause-all", json={"paused": True})
    assert response.status_code == 200
    assert response.json()["paused"] is True and response.json()["since"]
    assert client.get("/api/status").json()["pause_all"]["paused"] is True
    client.post("/api/pause-all", json={"paused": False})
    assert client.get("/api/status").json()["pause_all"]["paused"] is False


def test_pause_all_holds_telegram_send_queue(tmp_path):
    from src.job_sources.telegram.watcher import (
        PENDING_SENDS_FILE,
        TelegramWatcher,
        queue_telegram_send,
    )
    from src.utils.pause_all import set_paused

    queue_telegram_send(tmp_path, "anna_hr", "Здравствуйте", "link", 0, 0)
    watcher = TelegramWatcher.__new__(TelegramWatcher)
    watcher.output_folder = tmp_path
    watcher.parameters = {}
    set_paused(tmp_path, True)
    with patch(
        "src.job_sources.telegram.watcher.flush_pending_telegram_sends"
    ) as flush:
        watcher._flush_pending_sends()
    flush.assert_not_called()
    assert (tmp_path / PENDING_SENDS_FILE).exists()


def test_bot_pause_all_command(tmp_path):
    import main
    from src.utils.pause_all import is_paused

    params = {"outputFileDirectory": tmp_path}
    with patch.object(main, "send_notification") as send:
        main._run_control_commands(
            params, [{"action": "pause", "source": "all"}], "t", "1"
        )
        assert is_paused(tmp_path)
        main._run_control_commands(
            params, [{"action": "resume", "source": "all"}], "t", "1"
        )
    assert not is_paused(tmp_path)
    assert "Пауза снята" in send.call_args.args[2]


# --- «Это была ошибка» и «Откликнуться всё равно» --------------------------


def _log_with_skip(out: Path):
    from src.job import Job
    from src.job_sources.applied_log import AppliedLog

    log = AppliedLog(out / "applied_log.json")
    job = Job(
        role="Python Developer",
        company="Nova Tech",
        link="https://hh.ru/vacancy/1",
        source="headhunter",
        external_id="1",
    )
    log.record(job, "", "", "skipped_low_fit", 3, ["Нет Kubernetes"])
    return log, job


def test_feedback_mark_round_trip_and_reaches_scoring(client):  # noqa: F811
    from src.job_sources import job_fit
    from src.job_sources.llm_usage import set_output_folder

    out = api.get_ctx().output_folder
    _, job = _log_with_skip(out)
    response = client.post(
        "/api/applications/feedback",
        json={
            "source": "headhunter",
            "external_id": "1",
            "verdict": "should_apply",
            "reason": "Kubernetes не обязателен",
        },
    )
    assert response.status_code == 200
    assert response.json()["feedback"]["verdict"] == "should_apply"
    (entry,) = client.get("/api/applications").json()
    assert entry["feedback"]["reason"] == "Kubernetes не обязателен"

    set_output_folder(out)
    try:
        lines, forced = job_fit._decision_feedback(job)
    finally:
        set_output_folder(None)
    assert "Nova Tech" in lines and "стоило откликнуться" in lines
    assert "Kubernetes не обязателен" in lines and forced is False

    client.post(
        "/api/applications/feedback",
        json={"source": "headhunter", "external_id": "1", "verdict": ""},
    )
    (entry,) = client.get("/api/applications").json()
    assert "feedback" not in entry


def test_feedback_rejects_unknown_verdict_and_missing_entry(
    client,  # noqa: F811
):
    bad = client.post(
        "/api/applications/feedback",
        json={"source": "hh", "external_id": "x", "verdict": "maybe"},
    )
    assert bad.status_code == 400
    missing = client.post(
        "/api/applications/feedback",
        json={"source": "hh", "external_id": "x", "verdict": "should_skip"},
    )
    assert missing.status_code == 404


def test_apply_anyway_skips_scoring_and_replaces_skip(tmp_path):
    from src.job_sources import job_fit
    from src.job_sources.llm_usage import set_output_folder

    log, job = _log_with_skip(tmp_path)
    assert log.already_applied(job) is True
    log.set_feedback("headhunter", "1", "should_apply", "подходит")
    log.set_apply_anyway("headhunter", "1", True)
    # Площадка снова видит вакансию — и не отбрасывает её как виденную.
    assert log.already_applied(job) is False

    set_output_folder(tmp_path)
    try:
        with patch.object(job_fit, "get_chat_llm") as llm:
            fit = job_fit.score_job_fit(Path("нет.pdf"), job, "key")
    finally:
        set_output_folder(None)
    llm.assert_not_called()
    assert fit.score == 10

    log.record(job, "письмо", "", "applied", 10, [])
    entries = log.find_by_company("")
    assert [e["status"] for e in entries] == ["applied"]
    assert entries[0]["apply_anyway"] is True
    assert entries[0]["feedback"]["verdict"] == "should_apply"
    assert log.already_applied(job) is True


def test_apply_anyway_api(client):  # noqa: F811
    out = api.get_ctx().output_folder
    log, job = _log_with_skip(out)
    response = client.post(
        "/api/applications/apply-anyway",
        json={"source": "headhunter", "external_id": "1"},
    )
    assert response.status_code == 200
    assert response.json()["apply_anyway"] is True
    log.record(job, "письмо", "", "applied", 10, [])
    again = client.post(
        "/api/applications/apply-anyway",
        json={"source": "headhunter", "external_id": "1"},
    )
    assert again.status_code == 409


# --- Telegram в «Общении» ---------------------------------------------------


def _watcher(tmp: Path, **telegram):
    from src.job_sources.telegram import watcher as w

    watcher = w.TelegramWatcher(
        1,
        "h",
        tmp / "s",
        [],
        ["python"],
        [],
        "me",
        {
            "outputFileDirectory": tmp,
            "dataFolder": tmp,
            "telegram": telegram,
        },
    )
    return watcher


def _post_event(text, msg_id=5, channel="geekjobs"):
    from types import SimpleNamespace

    async def get_chat():
        return SimpleNamespace(username=channel)

    return SimpleNamespace(
        message=SimpleNamespace(message=text, id=msg_id),
        chat_id=1,
        get_chat=get_chat,
    )


class _Client:
    def __init__(self):
        self.forwarded, self.sent = [], []

    async def forward_messages(self, target, message):
        from types import SimpleNamespace

        self.forwarded.append(message.id)
        return SimpleNamespace(id=9)

    async def send_message(self, target, text, **kw):
        self.sent.append(text)


def test_posts_without_bot_are_saved_for_talk_view(client):  # noqa: F811
    import asyncio

    out = api.get_ctx().output_folder
    watcher = _watcher(out)
    watcher.client = _Client()
    asyncio.run(
        watcher._on_channel_post(
            _post_event("Python Dev в Acme, пишите @anna_hr", msg_id=5)
        )
    )
    asyncio.run(
        watcher._on_channel_post(
            _post_event("Ищем Python backend, @bob_hr", msg_id=6)
        )
    )
    body = client.get("/api/telegram/posts").json()
    assert [p["link"] for p in body["posts"]] == [
        "https://t.me/geekjobs/6",
        "https://t.me/geekjobs/5",
    ]
    first = body["posts"][0]
    assert first["saved_at"] and first["contacts"][0]["value"] == "bob_hr"
    assert first["draft"] is None and first["scheduled"] is None
    assert body["daily_limit"] == 15

    client.post(f"/api/telegram/posts/{first['id']}/hide", json={})
    links = [
        p["link"] for p in client.get("/api/telegram/posts").json()["posts"]
    ]
    assert links == ["https://t.me/geekjobs/5"]


def _saved_post(out: Path) -> str:
    from src.job_sources.telegram.watcher import save_watch_post

    return save_watch_post(
        out,
        {
            "channel": "geekjobs",
            "link": "https://t.me/geekjobs/7",
            "title": "Python Dev в Acme",
            "text": "Python Dev в Acme, пишите @anna_hr",
            "contacts": [{"kind": "telegram", "value": "anna_hr"}],
        },
    )


def test_post_draft_then_rewrite_replaces_it(client):  # noqa: F811
    out = api.get_ctx().output_folder
    post_id = _saved_post(out)
    texts = iter(["Первый вариант", "Второй вариант"])
    with patch.object(
        api,
        "generate_first_message",
        side_effect=lambda *a, **k: {"subject": "", "text": next(texts)},
    ), patch.object(api, "candidate_name", return_value="Иван"):
        first = client.post(f"/api/telegram/posts/{post_id}/draft", json={})
        second = client.post(f"/api/telegram/posts/{post_id}/draft", json={})
    assert first.status_code == 200, first.text
    assert first.json()["text"] == "Первый вариант"
    assert first.json()["contact"] == "anna_hr"
    assert first.json()["post_id"] == post_id
    (post,) = client.get("/api/telegram/posts").json()["posts"]
    assert post["draft"]["text"] == "Второй вариант"
    assert post["draft"]["code"] == second.json()["code"]


def test_send_later_queues_for_morning_and_cancel_restores_draft(
    client,  # noqa: F811
):
    from main import HR_DRAFTS_FILE
    from src.job_sources.hr_replies import DraftStore
    from src.job_sources.telegram.watcher import pending_telegram_sends

    out = api.get_ctx().output_folder
    post_id = _saved_post(out)
    code = DraftStore(out / HR_DRAFTS_FILE).add(
        "anna_hr",
        "Черновик",
        "first",
        "https://t.me/geekjobs/7",
        post_id=post_id,
    )
    response = client.post(
        f"/api/hr-drafts/{code}/later", json={"text": "Правленый текст"}
    )
    assert response.status_code == 200, response.text
    when = datetime.fromisoformat(response.json()["send_after"])
    assert (when.hour, when.minute) == (10, 0)
    assert DraftStore(out / HR_DRAFTS_FILE).get(code) is None
    (entry,) = pending_telegram_sends(out).values()
    assert entry["text"] == "Правленый текст" and entry["scheduled"]
    (post,) = client.get("/api/telegram/posts").json()["posts"]
    assert post["scheduled"]["id"] == response.json()["id"]

    cancelled = client.delete(
        f"/api/telegram/scheduled/{response.json()['id']}"
    )
    assert cancelled.status_code == 200
    restored = DraftStore(out / HR_DRAFTS_FILE).get(cancelled.json()["code"])
    assert restored["text"] == "Правленый текст"
    assert restored["post_id"] == post_id
    assert pending_telegram_sends(out) == {}


def test_flush_claims_due_entries_once(tmp_path):
    from src.job_sources.telegram.watcher import (
        flush_pending_telegram_sends,
        queue_telegram_send,
    )

    queue_telegram_send(tmp_path, "anna_hr", "Привет", "link", 0, 0)
    sent = []
    for _ in range(2):
        flush_pending_telegram_sends(
            lambda contact, text: sent.append((contact, text)),
            tmp_path,
            None,
        )
    assert sent == [("anna_hr", "Привет")]


def test_night_hold_and_next_morning():
    from src.job_sources.telegram.watcher import next_morning, night_hold

    night = datetime(2026, 10, 8, 2, 0).astimezone()
    day = datetime(2026, 10, 8, 14, 0).astimezone()
    assert night_hold({"night_to_morning": True}, night) is True
    assert night_hold({"night_to_morning": True}, day) is False
    assert night_hold({}, night) is False
    custom = {
        "night_to_morning": True,
        "active_hours_start": 10,
        "active_hours_end": 20,
    }
    assert night_hold(custom, datetime(2026, 10, 8, 9).astimezone()) is True
    assert next_morning(night).hour == 10 and next_morning(night).day == 8
    assert next_morning(day).day == 9


def test_night_posts_wait_for_morning_then_go_to_bot(tmp_path, monkeypatch):
    import asyncio

    from src.job_sources.telegram import watcher as w

    sent = []
    monkeypatch.setattr(
        w, "bot_request", lambda token, method, payload: sent.append(payload)
    )
    watcher = _watcher(tmp_path, night_to_morning=True)
    watcher.bot = ("T", "42")
    watcher.client = _Client()
    monkeypatch.setattr(w, "night_hold", lambda prefs, now=None: True)
    asyncio.run(
        watcher._on_channel_post(_post_event("Python Dev, пишите @anna_hr"))
    )
    assert sent == [] and w.night_posts_count(tmp_path) == 1
    monkeypatch.setattr(w, "night_hold", lambda prefs, now=None: False)
    watcher._deliver_night_posts()
    assert len(sent) == 1 and "Python Dev" in sent[0]["text"]
    assert w.night_posts_count(tmp_path) == 0


def test_preview_before_send_makes_draft_instead_of_queue(
    tmp_path, monkeypatch
):
    import asyncio

    from main import HR_DRAFTS_FILE
    from src.job_sources.hr_replies import DraftStore
    from src.job_sources.telegram import watcher as w

    sent = []
    monkeypatch.setattr(
        w, "bot_request", lambda token, method, payload: sent.append(payload)
    )
    monkeypatch.setattr(w, "get_or_create_topic", lambda *a, **k: None)
    watcher = _watcher(tmp_path, auto_message=True, preview_before_send=True)
    watcher.bot = ("T", "42")
    watcher.client = _Client()
    monkeypatch.setattr(
        watcher,
        "_auto_message_text",
        lambda title, text, link: ("Текст от ИИ", ""),
    )
    asyncio.run(
        watcher._on_channel_post(_post_event("Python Dev, пишите @anna_hr"))
    )
    assert w.pending_telegram_sends(tmp_path) == {}
    ((code, draft),) = DraftStore(tmp_path / HR_DRAFTS_FILE).all().items()
    assert draft["text"] == "Текст от ИИ" and draft["contact"] == "anna_hr"
    (payload,) = sent
    buttons = payload["reply_markup"]["inline_keyboard"][0]
    assert buttons[0]["callback_data"] == f"d:{code}:-1"


def test_preview_settings_round_trip(client):  # noqa: F811
    response = client.post(
        "/api/settings/telegram-watch",
        json={"preview_before_send": True, "night_to_morning": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["preview_before_send"] is True
    assert body["night_to_morning"] is True


def test_suggest_replies_endpoint(client):  # noqa: F811
    from src.job_sources.telegram_conversations import TelegramConversations

    out = api.get_ctx().output_folder
    conv = TelegramConversations(out / "telegram_conversations.json")
    conv.record_outbound("anna_hr", "Здравствуйте! Интересна вакансия")
    conv.record_inbound(
        "anna_hr", "Когда удобно созвониться?", 2, datetime.now()
    )
    fake = [
        {
            "label": "Завтра в 11",
            "text": "Завтра в 11 удобно",
            "attach_resume": False,
        }
    ]
    with patch(
        "src.job_sources.reply_answerer.suggest_replies", return_value=fake
    ) as suggest:
        response = client.post("/api/telegram/conversations/anna_hr/suggest")
    assert response.status_code == 200, response.text
    assert response.json()["suggestions"] == fake
    messages = suggest.call_args.args[1]
    assert messages[-1]["text"] == "Когда удобно созвониться?"


def test_do_not_contact_from_talk_creates_and_marks_card(
    client,  # noqa: F811
):
    from src.job_sources.contact_book import ContactBook

    out = api.get_ctx().output_folder
    post_id = _saved_post(out)
    response = client.post(
        "/api/contacts/do-not-contact",
        json={"value": "@anna_hr", "post_id": post_id},
    )
    assert response.status_code == 200, response.text
    (key,) = response.json()["keys"]
    assert ContactBook(out).all()[key]["do_not_contact"] is True
    client.post(
        "/api/contacts/do-not-contact",
        json={"value": "anna_hr", "on": False},
    )
    assert ContactBook(out).all()[key]["do_not_contact"] is False
