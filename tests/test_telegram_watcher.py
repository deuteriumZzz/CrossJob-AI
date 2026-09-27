import asyncio
import tempfile
from pathlib import Path
from types import SimpleNamespace

from src.job_sources.contact_book import ContactBook
from src.job_sources.telegram import watcher as w
from src.job_sources.telegram.client import TelegramSourceClient
from src.job_sources.telegram_conversations import TelegramConversations
from src.webui import api
from tests.test_webui_api import client  # noqa: F401  (fixture)


def test_match_keywords_and_defaults():
    assert w.match_keywords(
        "Ищем Python backend-разработчика", ["python", "go"], []
    ) == ["python"]
    assert (
        w.match_keywords("Python, офис в Москве", ["python"], ["офис"]) == []
    )
    assert w.match_keywords("Java developer", ["python"], []) == []
    assert w.default_keywords(["Python разработчик", "Backend developer"]) == [
        "python",
        "backend",
    ]


class _FakeClient:
    def __init__(self, history=None):
        self.forwarded, self.sent = [], []
        self._history = history or []

    async def forward_messages(self, target, message):
        self.forwarded.append((target, message.id))
        return SimpleNamespace(id=999)

    async def send_message(self, target, text, **kw):
        self.sent.append((target, text, kw.get("reply_to")))
        return SimpleNamespace(id=1000)

    async def iter_messages(self, entity, limit=300):
        for message in self._history:
            yield message


def _event(text, msg_id=5, channel="geekjobs"):
    async def get_chat():
        return SimpleNamespace(username=channel)

    return SimpleNamespace(
        message=SimpleNamespace(message=text, id=msg_id),
        chat_id=1,
        get_chat=get_chat,
    )


def test_channel_post_forwarded_with_header_once():
    with tempfile.TemporaryDirectory() as tmp:
        watcher = w.TelegramWatcher(
            1,
            "h",
            Path(tmp) / "s",
            ["geekjobs"],
            ["python"],
            ["1с"],
            "me",
            {"outputFileDirectory": Path(tmp), "dataFolder": Path(tmp)},
        )
        watcher.client = _FakeClient()
        post = (
            "Acme ищет Python-разработчика. Пишите @anna_hr или jobs@acme.io"
        )
        asyncio.run(watcher._on_channel_post(_event(post)))
        asyncio.run(
            watcher._on_channel_post(_event(post, msg_id=6, channel="other"))
        )  # репост
        asyncio.run(watcher._on_channel_post(_event("Java 1С developer")))

        assert watcher.client.forwarded == [("me", 5)]
        [(target, header, reply_to)] = watcher.client.sent
        assert target == "me" and reply_to == 999
        assert header.startswith("🎯 python · @geekjobs")
        assert "@anna_hr" in header and "jobs@acme.io" in header
        assert watcher.matched_count == 1
        [card] = ContactBook(Path(tmp)).all().values()
        assert {c["value"] for c in card["contacts"]} == {
            "anna_hr",
            "jobs@acme.io",
        }


def test_backfilled_channels_persist_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        assert w._load_backfilled_channels(out) == set()
        w._save_backfilled_channels(out, {"geekjobs", "acme_jobs"})
        assert w._load_backfilled_channels(out) == {"geekjobs", "acme_jobs"}


def test_backfill_channel_only_forwards_recent_matches():
    """Досмотр истории нового канала: старее channel_backfill_days —
    пропускаем; новее и по ключевым словам — идёт через тот же путь,
    что и живой пост (форвард), включая дедуп по _seen."""
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    history = [
        SimpleNamespace(message="Ищем Python-разработчика", id=10, date=now),
        SimpleNamespace(
            message="Java 1С developer", id=11, date=now
        ),  # стоп-слово — не совпадает
        SimpleNamespace(
            message="Ищем Python-разработчика (старый)",
            id=12,
            date=now - timedelta(days=30),
        ),  # старше окна — до него цикл вообще не доходит (break)
    ]
    with tempfile.TemporaryDirectory() as tmp:
        watcher = w.TelegramWatcher(
            1,
            "h",
            Path(tmp) / "s",
            ["geekjobs"],
            ["python"],
            ["1с"],
            "me",
            {
                "outputFileDirectory": Path(tmp),
                "dataFolder": Path(tmp),
                "telegram": {"channel_backfill_days": 14},
            },
        )
        watcher.client = _FakeClient(history=history)
        asyncio.run(watcher._backfill_channel(object(), "geekjobs"))
        assert watcher.client.forwarded == [("me", 10)]


def test_source_client_routes_through_active_watcher(monkeypatch):
    calls = []

    class _Watcher:
        connected = True

        def call(self, factory, timeout=60):
            calls.append(factory)
            return "sent"

    monkeypatch.setattr(w, "_ACTIVE", _Watcher())
    with tempfile.TemporaryDirectory() as tmp:
        with TelegramSourceClient(1, "h", Path(tmp) / "session") as tg:
            assert tg.send_message("hr_anna", "Привет") == "sent"
    assert len(calls) == 1


def test_watch_settings_api(client):  # noqa: F811
    snap = client.get("/api/settings/telegram-watch").json()
    assert snap["enabled"] is False and snap["running"] is False
    snap = client.post(
        "/api/settings/telegram-watch",
        json={
            "enabled": True,
            "keywords": ["python", " django "],
            "stop_words": ["офис"],
            "forward_to": "@my_jobs",
        },
    ).json()
    assert snap["enabled"] is True
    assert snap["keywords"] == ["python", "django"]
    assert snap["stop_words"] == ["офис"]
    assert snap["forward_to"] == "my_jobs"
    tg = api.get_ctx().config["telegram"]
    assert tg["watch_enabled"] is True


def test_telegram_resumes_folder_and_keyboard():
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp)
        (data / "resume.pdf").write_bytes(b"%PDF")
        assert [p.name for p in w.telegram_resumes(data)] == ["resume.pdf"]
        (data / "telegram").mkdir()
        (data / "telegram" / "backend_ru.pdf").write_bytes(b"%PDF")
        (data / "telegram" / "backend_en.pdf").write_bytes(b"%PDF")
        resumes = w.telegram_resumes(data)
        assert [p.name for p in resumes] == [
            "backend_en.pdf",
            "backend_ru.pdf",
        ]

        kb = w.vacancy_keyboard(
            "abc",
            [
                {"kind": "telegram", "value": "anna_hr"},
                {"kind": "email", "value": "hr@acme.io"},
            ],
            resumes,
        )
        rows = kb["inline_keyboard"]
        assert [b["callback_data"] for b in rows[0]] == [
            "q:abc:0:-1",
            "q:abc:0:0",
            "q:abc:0:1",
        ]
        assert rows[1][0]["callback_data"] == "l:abc:0"
        assert rows[2][0]["callback_data"] == "l:abc:1"
        assert all(
            len(b["callback_data"].encode()) <= 64 for r in rows for b in r
        )


def _button_env(tmp, monkeypatch):
    import main

    data, out = Path(tmp) / "data", Path(tmp) / "out"
    data.mkdir()
    out.mkdir()
    (data / "telegram").mkdir()
    (data / "telegram" / "cv_ru.pdf").write_bytes(b"%PDF")
    (data / main.PLAIN_TEXT_RESUME_YAML).write_text(
        "personal_information:\n  name: Ann\n  surname: K\n", encoding="utf-8"
    )
    secrets = data / "secrets.yaml"
    secrets.write_text(
        "telegram:\n  api_id: 1\n  api_hash: h\n", encoding="utf-8"
    )
    params = {
        "dataFolder": data,
        "outputFileDirectory": out,
        "secretsFile": secrets,
        "telegram": {
            "intro_message_template": "Здравствуйте! Вакансия «{role}» {link}"
        },
    }
    post_id = w.save_watch_post(
        out,
        {
            "channel": "geekjobs",
            "link": "https://t.me/geekjobs/5",
            "title": "Python Dev",
            "text": "Acme ищет Python Dev. @anna_hr",
            "contacts": [{"kind": "telegram", "value": "anna_hr"}],
        },
    )
    calls = {"bot": [], "sent": [], "files": []}

    class _Client:
        def __init__(self, *a):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *e):
            return False

        def send_message(self, contact, text):
            calls["sent"].append((contact, text))

        def send_file(self, contact, path, caption=""):
            calls["files"].append((contact, Path(path).name))

    monkeypatch.setattr(main, "TelegramSourceClient", _Client)
    monkeypatch.setattr(
        main,
        "bot_request",
        lambda token, method, payload: calls["bot"].append((method, payload))
        or {},
    )
    cb = lambda data_: {  # noqa: E731
        "id": "cq1",
        "data": data_,
        "message": {"chat": {"id": 42}, "message_id": 7},
    }
    return main, params, post_id, calls, cb


def test_quick_hello_with_resume(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        main, params, post_id, calls, cb = _button_env(tmp, monkeypatch)
        main._handle_vacancy_button(params, "key", "T", cb(f"q:{post_id}:0:0"))
        assert calls["sent"] == [
            (
                "anna_hr",
                "Здравствуйте! Вакансия «Python Dev» https://t.me/geekjobs/5",
            )
        ]
        assert calls["files"] == [("anna_hr", "cv_ru.pdf")]
        edited = [p for m, p in calls["bot"] if m == "editMessageReplyMarkup"][
            0
        ]
        assert (
            "✅ Отправлено @anna_hr + резюме"
            in edited["reply_markup"]["inline_keyboard"][0][0]["text"]
        )
        conv = TelegramConversations(
            params["outputFileDirectory"] / "telegram_conversations.json"
        )
        assert (
            conv.get("anna_hr")["messages"][0]["job_link"]
            == "https://t.me/geekjobs/5"
        )


def test_quick_hello_uses_configured_resume_for_post_language(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        main, params, _, calls, cb = _button_env(tmp, monkeypatch)
        data = params["dataFolder"]
        (data / "telegram" / "selected_en.pdf").write_bytes(b"%PDF")
        params["resume_routing"] = {
            "telegram_ru": "telegram/cv_ru.pdf",
            "telegram_en": "telegram/selected_en.pdf",
        }
        post_id = w.save_watch_post(
            params["outputFileDirectory"],
            {
                "channel": "jobs",
                "link": "https://t.me/jobs/10",
                "title": "Backend Engineer",
                "text": "Acme is hiring a Backend Engineer. Contact @anna_hr",
                "contacts": [{"kind": "telegram", "value": "anna_hr"}],
            },
        )

        main._handle_vacancy_button(params, "key", "T", cb(f"q:{post_id}:0:0"))

        assert calls["files"] == [("anna_hr", "selected_en.pdf")]


def test_stale_resume_button_fails_without_sending(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        main, params, post_id, calls, cb = _button_env(tmp, monkeypatch)
        (params["dataFolder"] / "telegram" / "cv_ru.pdf").unlink()

        main._handle_vacancy_button(params, "key", "T", cb(f"q:{post_id}:0:0"))

        assert calls["sent"] == [] and calls["files"] == []
        edited = [
            payload
            for method, payload in calls["bot"]
            if method == "editMessageReplyMarkup"
        ][0]
        assert (
            "недоступно"
            in edited["reply_markup"]["inline_keyboard"][0][0]["text"]
        )


def test_llm_letter_saved_to_telegram_folder_then_sent(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        main, params, post_id, calls, cb = _button_env(tmp, monkeypatch)
        monkeypatch.setattr(
            main,
            "generate_first_message",
            lambda *a: {
                "subject": "s",
                "text": "Под вашу вакансию: 3 примера.",
            },
        )
        main._handle_vacancy_button(params, "key", "T", cb(f"l:{post_id}:0"))
        letters = list(
            (params["dataFolder"] / "telegram" / "letters").glob("*.txt")
        )
        assert len(letters) == 1 and "3 примера" in letters[0].read_text(
            encoding="utf-8"
        )
        draft_msg = [p for m, p in calls["bot"] if m == "sendMessage"][0]
        buttons = [
            b["callback_data"]
            for row in draft_msg["reply_markup"]["inline_keyboard"]
            for b in row
        ]
        send_with_cv = next(
            b for b in buttons if b.startswith("d:") and not b.endswith(":-1")
        )
        main._handle_vacancy_button(params, "key", "T", cb(send_with_cv))
        assert calls["sent"][-1] == (
            "anna_hr",
            "Под вашу вакансию: 3 примера.",
        )
        assert calls["files"] == [("anna_hr", "cv_ru.pdf")]
        skip = next(b for b in buttons if b.startswith("x:"))
        main._handle_vacancy_button(
            params, "key", "T", cb(skip)
        )  # уже отправлен — просто закрыть


def test_bot_delivery_sends_buttons(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        sent = []
        monkeypatch.setattr(
            w,
            "bot_request",
            lambda token, method, payload: sent.append(payload) or {},
        )
        watcher = w.TelegramWatcher(
            1,
            "h",
            Path(tmp) / "s",
            [],
            ["python"],
            [],
            "me",
            {"outputFileDirectory": Path(tmp), "dataFolder": Path(tmp)},
        )
        watcher.bot = ("T", "42")
        watcher.client = _FakeClient()
        asyncio.run(
            watcher._on_channel_post(
                _event("Python Dev в Acme, пишите @anna_hr")
            )
        )
        [payload] = sent
        assert (
            payload["chat_id"] == "42"
            and "🎯 python · @geekjobs" in payload["text"]
        )
        assert (
            payload["reply_markup"]["inline_keyboard"][0][0]["text"]
            == "👋 @anna_hr"
        )
        assert (
            watcher.client.forwarded == []
        )  # с ботом — без пересылки в «Избранное»


def test_email_letter_sent_via_gmail_with_chosen_resume(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        main, params, _, calls, cb = _button_env(tmp, monkeypatch)
        email_resume = params["dataFolder"] / "telegram" / "gmail_ru.pdf"
        email_resume.write_bytes(b"%PDF")
        params["resume_routing"] = {
            "telegram_ru": "telegram/cv_ru.pdf",
            "email_ru": "telegram/gmail_ru.pdf",
        }
        params["secretsFile"].write_text(
            "telegram:\n  api_id: 1\n  api_hash: h\nemail:\n  address: "
            "me@gmail.com\n  app_password: p\n",
            encoding="utf-8",
        )
        post_id = w.save_watch_post(
            params["outputFileDirectory"],
            {
                "channel": "jobs",
                "link": "https://t.me/jobs/9",
                "title": "Python Dev",
                "text": "Пишите jobs@acme.io",
                "contacts": [{"kind": "email", "value": "jobs@acme.io"}],
            },
        )
        monkeypatch.setattr(
            main,
            "generate_first_message",
            lambda *a: {"subject": "Python Dev — отклик", "text": "Письмо"},
        )
        mails = []
        monkeypatch.setattr(
            main, "send_email", lambda creds, m: mails.append(m) or "<id>"
        )
        main._handle_vacancy_button(params, "key", "T", cb(f"l:{post_id}:0"))
        draft_msg = [p for m, p in calls["bot"] if m == "sendMessage"][-1]
        buttons = [
            b["callback_data"]
            for b in draft_msg["reply_markup"]["inline_keyboard"][0]
        ]
        assert all(
            not b.endswith(":-1") for b in buttons
        )  # у письма резюме всегда
        main._handle_vacancy_button(params, "key", "T", cb(buttons[0]))
        [mail] = mails
        assert mail["To"] == "jobs@acme.io"
        assert mail.get_payload()[1].get_filename() == "gmail_ru.pdf"


def test_new_channels_picked_up_without_restart(tmp_path, monkeypatch):
    (tmp_path / "work_preferences.yaml").write_text(
        "telegram:\n  channels:\n    - 'old'\n    - "
        "'https://t.me/new_one'\n  watch_keywords: ['go']\n"
        "resume_routing:\n  telegram_en: telegram/new.pdf\n",
        encoding="utf-8",
    )
    tw = w.TelegramWatcher(
        1,
        "h",
        tmp_path / "s",
        ["old"],
        ["python"],
        [],
        "me",
        {
            "outputFileDirectory": tmp_path,
            "dataFolder": tmp_path,
            "secretsFile": tmp_path / "x",
        },
    )
    connected = iter([True, False])
    tw.client = SimpleNamespace(is_connected=lambda: next(connected))
    subscribed = []

    async def fake_subscribe():
        subscribed.append(list(tw.channels))

    async def no_sleep(_):
        pass

    monkeypatch.setattr(tw, "_subscribe", fake_subscribe)
    monkeypatch.setattr(w.asyncio, "sleep", no_sleep)
    asyncio.run(tw._watch_settings())
    assert subscribed == [["old", "new_one"]] and tw.keywords == ["go"]
    assert tw.parameters["resume_routing"] == {
        "telegram_en": "telegram/new.pdf"
    }


def test_email_from_post_marks_base_and_do_not_write(monkeypatch):
    """Письмо HR из поста парсера: в Базе «написали» (рассылка второй раз не
    напишет), ответ ловится; «Не писать компании» — статус «не писать»."""
    from src.job_sources.contact_book import ContactBook
    from src.webui.api import _contact_status

    with tempfile.TemporaryDirectory() as tmp:
        main, params, _, calls, cb = _button_env(tmp, monkeypatch)
        out = params["outputFileDirectory"]
        params["secretsFile"].write_text(
            "email:\n  address: me@gmail.com\n  app_password: p\n",
            encoding="utf-8",
        )
        (params["dataFolder"] / main.RESUME_PDF).write_bytes(b"%PDF")
        contact = {"kind": "email", "value": "HR@acme.io"}
        ContactBook(out).add(
            "Acme", [{**contact, "source": "пост в @geekjobs"}]
        )
        post_id = w.save_watch_post(
            out,
            {
                "channel": "geekjobs",
                "link": "https://t.me/geekjobs/6",
                "title": "Python Dev",
                "text": "Acme: HR@acme.io",
                "contacts": [contact],
            },
        )
        monkeypatch.setattr(
            main,
            "generate_first_message",
            lambda *a: {"subject": "Python Dev", "text": "Hi"},
        )
        monkeypatch.setattr(main, "build_message", lambda *a, **k: "msg")
        monkeypatch.setattr(main, "send_email", lambda creds, msg: "<id1>")
        main._handle_vacancy_button(params, "key", "T", cb(f"l:{post_id}:0"))
        draft_msg = [p for m, p in calls["bot"] if m == "sendMessage"][-1]
        buttons = [
            b["callback_data"]
            for row in draft_msg["reply_markup"]["inline_keyboard"]
            for b in row
        ]
        assert any(b.startswith("nd:") for b in buttons)
        main._handle_vacancy_button(
            params,
            "key",
            "T",
            cb(next(b for b in buttons if b.startswith("d:"))),
        )

        def status() -> str:
            return _contact_status(
                ContactBook(out).get("acme")["contacts"][0], {}, {}, set()
            )

        assert status() == "written"
        monkeypatch.setattr(
            main, "bounced_addresses", lambda creds, addrs: set()
        )
        monkeypatch.setattr(
            main, "senders_replied", lambda creds, addrs: {"hr@acme.io"}
        )
        monkeypatch.setattr(main, "notify", lambda *a: None)
        main._check_contact_book_mail(params, {})
        assert status() == "replied"

        main._handle_vacancy_button(params, "key", "T", cb(f"n:{post_id}"))
        assert ContactBook(out).get("acme")["do_not_contact"] is True


def test_pending_telegram_sends_queue_and_flush():
    """queue_telegram_send не блокирует (никакого sleep) — просто пишет
    запись с send_after; flush отправляет только то, чему пришло время
    и мы в рабочих часах, остальное остаётся в очереди."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        w.queue_telegram_send(
            out, "hr_user", "текст письма", "https://t.me/c/1", 0, 0
        )
        assert w.pending_telegram_sends_count(out) == 1

        sent = []
        # Заведомо не текущий час — ничего не уходит, запись остаётся.
        from datetime import datetime

        off_hour = (datetime.now().astimezone().hour + 12) % 24
        w.flush_pending_telegram_sends(
            lambda contact, text: sent.append((contact, text)),
            out,
            (off_hour, off_hour + 1),
        )
        assert sent == []
        assert w.pending_telegram_sends_count(out) == 1

        # Без ограничения часов и с нулевой задержкой — отправляется и
        # удаляется из очереди.
        w.flush_pending_telegram_sends(
            lambda contact, text: sent.append((contact, text)), out, None
        )
        assert sent == [("hr_user", "текст письма")]
        assert w.pending_telegram_sends_count(out) == 0
