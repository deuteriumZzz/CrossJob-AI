import asyncio
import tempfile
from pathlib import Path
from types import SimpleNamespace

from src.job_sources.contact_book import ContactBook
from src.job_sources.telegram_conversations import TelegramConversations
from src.job_sources.telegram import watcher as w
from src.job_sources.telegram.client import TelegramSourceClient
from src.webui import api
from tests.test_webui_api import client  # noqa: F401  (fixture)


def test_match_keywords_and_defaults():
    assert w.match_keywords("Ищем Python backend-разработчика", ["python", "go"], []) == ["python"]
    assert w.match_keywords("Python, офис в Москве", ["python"], ["офис"]) == []
    assert w.match_keywords("Java developer", ["python"], []) == []
    assert w.default_keywords(["Python разработчик", "Backend developer"]) == ["python", "backend"]


class _FakeClient:
    def __init__(self):
        self.forwarded, self.sent = [], []

    async def forward_messages(self, target, message):
        self.forwarded.append((target, message.id))
        return SimpleNamespace(id=999)

    async def send_message(self, target, text, **kw):
        self.sent.append((target, text, kw.get("reply_to")))
        return SimpleNamespace(id=1000)


def _event(text, msg_id=5, channel="geekjobs"):
    async def get_chat():
        return SimpleNamespace(username=channel)

    return SimpleNamespace(
        message=SimpleNamespace(message=text, id=msg_id), chat_id=1, get_chat=get_chat
    )


def test_channel_post_forwarded_with_header_once():
    with tempfile.TemporaryDirectory() as tmp:
        watcher = w.TelegramWatcher(
            1, "h", Path(tmp) / "s", ["geekjobs"], ["python"], ["1с"], "me",
            {"outputFileDirectory": Path(tmp), "dataFolder": Path(tmp)},
        )
        watcher.client = _FakeClient()
        post = "Acme ищет Python-разработчика. Пишите @anna_hr или jobs@acme.io"
        asyncio.run(watcher._on_channel_post(_event(post)))
        asyncio.run(watcher._on_channel_post(_event(post, msg_id=6, channel="other")))  # репост
        asyncio.run(watcher._on_channel_post(_event("Java 1С developer")))

        assert watcher.client.forwarded == [("me", 5)]
        [(target, header, reply_to)] = watcher.client.sent
        assert target == "me" and reply_to == 999
        assert header.startswith("🎯 python · @geekjobs")
        assert "@anna_hr" in header and "jobs@acme.io" in header
        assert watcher.matched_count == 1
        [card] = ContactBook(Path(tmp)).all().values()
        assert {c["value"] for c in card["contacts"]} == {"anna_hr", "jobs@acme.io"}


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
    snap = client.post("/api/settings/telegram-watch", json={
        "enabled": True, "keywords": ["python", " django "], "stop_words": ["офис"],
        "forward_to": "@my_jobs",
    }).json()
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
        assert [p.name for p in resumes] == ["backend_en.pdf", "backend_ru.pdf"]

        kb = w.vacancy_keyboard("abc", [{"kind": "telegram", "value": "anna_hr"},
                                        {"kind": "email", "value": "hr@acme.io"}], resumes)
        rows = kb["inline_keyboard"]
        assert [b["callback_data"] for b in rows[0]] == ["q:abc:0:-1", "q:abc:0:0", "q:abc:0:1"]
        assert rows[1][0]["callback_data"] == "l:abc:0"
        assert rows[2][0]["callback_data"] == "l:abc:1"
        assert all(len(b["callback_data"].encode()) <= 64 for r in rows for b in r)


def _button_env(tmp, monkeypatch):
    import main

    data, out = Path(tmp) / "data", Path(tmp) / "out"
    data.mkdir(); out.mkdir()
    (data / "telegram").mkdir()
    (data / "telegram" / "cv_ru.pdf").write_bytes(b"%PDF")
    (data / main.PLAIN_TEXT_RESUME_YAML).write_text(
        "personal_information:\n  name: Ann\n  surname: K\n", encoding="utf-8")
    secrets = data / "secrets.yaml"
    secrets.write_text("telegram:\n  api_id: 1\n  api_hash: h\n", encoding="utf-8")
    params = {"dataFolder": data, "outputFileDirectory": out, "secretsFile": secrets,
              "telegram": {"intro_message_template": "Здравствуйте! Вакансия «{role}» {link}"}}
    post_id = w.save_watch_post(out, {
        "channel": "geekjobs", "link": "https://t.me/geekjobs/5", "title": "Python Dev",
        "text": "Acme ищет Python Dev. @anna_hr", "contacts": [{"kind": "telegram", "value": "anna_hr"}],
    })
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
    monkeypatch.setattr(main, "bot_request", lambda token, method, payload: calls["bot"].append((method, payload)) or {})
    cb = lambda data_: {"id": "cq1", "data": data_, "message": {"chat": {"id": 42}, "message_id": 7}}
    return main, params, post_id, calls, cb


def test_quick_hello_with_resume(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        main, params, post_id, calls, cb = _button_env(tmp, monkeypatch)
        main._handle_vacancy_button(params, "key", "T", cb(f"q:{post_id}:0:0"))
        assert calls["sent"] == [("anna_hr", "Здравствуйте! Вакансия «Python Dev» https://t.me/geekjobs/5")]
        assert calls["files"] == [("anna_hr", "cv_ru.pdf")]
        edited = [p for m, p in calls["bot"] if m == "editMessageReplyMarkup"][0]
        assert "✅ Отправлено @anna_hr + резюме" in edited["reply_markup"]["inline_keyboard"][0][0]["text"]
        conv = TelegramConversations(params["outputFileDirectory"] / "telegram_conversations.json")
        assert conv.get("anna_hr")["messages"][0]["job_link"] == "https://t.me/geekjobs/5"


def test_llm_letter_saved_to_telegram_folder_then_sent(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        main, params, post_id, calls, cb = _button_env(tmp, monkeypatch)
        monkeypatch.setattr(main, "generate_first_message",
                            lambda *a: {"subject": "s", "text": "Под вашу вакансию: 3 примера."})
        main._handle_vacancy_button(params, "key", "T", cb(f"l:{post_id}:0"))
        letters = list((params["dataFolder"] / "telegram" / "letters").glob("*.txt"))
        assert len(letters) == 1 and "3 примера" in letters[0].read_text(encoding="utf-8")
        draft_msg = [p for m, p in calls["bot"] if m == "sendMessage"][0]
        buttons = [b["callback_data"] for row in draft_msg["reply_markup"]["inline_keyboard"] for b in row]
        send_with_cv = next(b for b in buttons if b.startswith("d:") and not b.endswith(":-1"))
        main._handle_vacancy_button(params, "key", "T", cb(send_with_cv))
        assert calls["sent"][-1] == ("anna_hr", "Под вашу вакансию: 3 примера.")
        assert calls["files"] == [("anna_hr", "cv_ru.pdf")]
        skip = next(b for b in buttons if b.startswith("x:"))
        main._handle_vacancy_button(params, "key", "T", cb(skip))  # уже отправлен — просто закрыть


def test_bot_delivery_sends_buttons(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        sent = []
        monkeypatch.setattr(w, "bot_request", lambda token, method, payload: sent.append(payload) or {})
        watcher = w.TelegramWatcher(1, "h", Path(tmp) / "s", [], ["python"], [], "me",
                                    {"outputFileDirectory": Path(tmp), "dataFolder": Path(tmp)})
        watcher.bot = ("T", "42")
        watcher.client = _FakeClient()
        asyncio.run(watcher._on_channel_post(_event("Python Dev в Acme, пишите @anna_hr")))
        [payload] = sent
        assert payload["chat_id"] == "42" and "🎯 python · @geekjobs" in payload["text"]
        assert payload["reply_markup"]["inline_keyboard"][0][0]["text"] == "👋 @anna_hr"
        assert watcher.client.forwarded == []  # с ботом — без пересылки в «Избранное»


def test_email_letter_sent_via_gmail_with_chosen_resume(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        main, params, _, calls, cb = _button_env(tmp, monkeypatch)
        params["secretsFile"].write_text(
            "telegram:\n  api_id: 1\n  api_hash: h\nemail:\n  address: me@gmail.com\n  app_password: p\n",
            encoding="utf-8")
        post_id = w.save_watch_post(params["outputFileDirectory"], {
            "channel": "jobs", "link": "https://t.me/jobs/9", "title": "Python Dev",
            "text": "Пишите jobs@acme.io", "contacts": [{"kind": "email", "value": "jobs@acme.io"}],
        })
        monkeypatch.setattr(main, "generate_first_message",
                            lambda *a: {"subject": "Python Dev — отклик", "text": "Письмо"})
        mails = []
        monkeypatch.setattr(main, "send_email", lambda creds, m: mails.append(m) or "<id>")
        main._handle_vacancy_button(params, "key", "T", cb(f"l:{post_id}:0"))
        draft_msg = [p for m, p in calls["bot"] if m == "sendMessage"][-1]
        buttons = [b["callback_data"] for b in draft_msg["reply_markup"]["inline_keyboard"][0]]
        assert all(not b.endswith(":-1") for b in buttons)  # у письма резюме всегда
        main._handle_vacancy_button(params, "key", "T", cb(buttons[0]))
        [mail] = mails
        assert mail["To"] == "jobs@acme.io"
        assert mail.get_payload()[1].get_filename() == "cv_ru.pdf"
