import asyncio
import tempfile
from pathlib import Path
from types import SimpleNamespace

from src.job_sources.contact_book import ContactBook
from src.job_sources.telegram import watcher as w
from src.job_sources.telegram.client import _SESSION_LOCK, TelegramSourceClient
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


def test_llm_check_post_is_unavailable_without_key():
    assert w._llm_check_post("любой текст", "") is None


def test_llm_check_post_is_unavailable_on_error(monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("no llm configured")

    monkeypatch.setattr("src.job_sources.llm_provider.get_chat_llm", _boom)
    assert w._llm_check_post("любой текст", "key") is None


def test_llm_check_post_retries_on_rate_limit_then_succeeds(monkeypatch):
    """Всплеск запросов (много каналов разом) не должен превращаться в
    мгновенный «ИИ недоступен» — ждём сброса лимита и пробуем снова."""
    monkeypatch.setattr(w, "RATE_LIMIT_RETRY_DELAYS_SECONDS", (0, 0))
    sleeps: list[float] = []
    monkeypatch.setattr(w.time, "sleep", sleeps.append)

    calls = {"n": 0}

    class _FakeLLM:
        def invoke(self, prompt):
            calls["n"] += 1
            if calls["n"] < 3:
                raise RuntimeError("Error 429: rate limit exceeded")
            return SimpleNamespace(content="ДА")

    monkeypatch.setattr(
        "src.job_sources.llm_provider.get_chat_llm",
        lambda *a, **kw: _FakeLLM(),
    )
    assert w._llm_check_post("Ищем Python-разработчика", "key") == (True, "")
    assert calls["n"] == 3
    assert sleeps == [0, 0]


def test_llm_check_post_is_unavailable_after_exhausting_retries(monkeypatch):
    monkeypatch.setattr(w, "RATE_LIMIT_RETRY_DELAYS_SECONDS", (0,))
    monkeypatch.setattr(w.time, "sleep", lambda *a: None)

    def _always_rate_limited(*args, **kwargs):
        raise RuntimeError("429 Too Many Requests")

    monkeypatch.setattr(
        "src.job_sources.llm_provider.get_chat_llm", _always_rate_limited
    )
    assert w._llm_check_post("текст", "key") is None


def test_llm_check_post_parses_short_answer(monkeypatch):
    class _FakeLLM:
        def invoke(self, prompt):
            assert "Пост:" in prompt
            return SimpleNamespace(content="НЕТ, это резюме кандидата")

    monkeypatch.setattr(
        "src.job_sources.llm_provider.get_chat_llm",
        lambda *a, **kw: _FakeLLM(),
    )
    assert w._llm_check_post("Ищу работу", "key") == (False, "")


def test_handle_post_skips_llm_call_when_flag_disabled(monkeypatch):
    called = []
    monkeypatch.setattr(
        w, "_llm_check_post", lambda *a, **kw: called.append(1) or (True, "")
    )
    with tempfile.TemporaryDirectory() as tmp:
        watcher = w.TelegramWatcher(
            1,
            "h",
            Path(tmp) / "s",
            ["geekjobs"],
            ["python"],
            [],
            "me",
            {"outputFileDirectory": Path(tmp), "dataFolder": Path(tmp)},
        )
        watcher.client = _FakeClient()
        asyncio.run(
            watcher._on_channel_post(_event("Ищем Python-разработчика"))
        )
    assert called == []


def test_enabled_llm_checks_every_keyword_match_including_structured_post(
    monkeypatch,
):
    """The safety switch must not bypass a post merely because it has
    salary and remote-work markers."""
    called = []
    monkeypatch.setattr(
        w, "_llm_check_post", lambda *a, **kw: called.append(1) or (True, "")
    )
    with tempfile.TemporaryDirectory() as tmp:
        watcher = w.TelegramWatcher(
            1,
            "h",
            Path(tmp) / "s",
            ["geekjobs"],
            ["python"],
            [],
            "me",
            {
                "outputFileDirectory": Path(tmp),
                "dataFolder": Path(tmp),
                "telegram": {"llm_vacancy_filter": True},
            },
        )
        watcher.client = _FakeClient()
        asyncio.run(
            watcher._on_channel_post(
                _event("Ищем Python-разработчика, 250000 ₽, удалённо")
            )
        )
    assert called == [1]


def test_match_keywords_rejects_candidate_self_posts():
    """Инцидент: пост "Ищу работу Python-разработчиком" совпал по
    ключевому слову "python" (законно — кандидат написал свою
    специализацию), но это не вакансия — контакт из такого поста не
    должен уходить в Базу компаний."""
    assert (
        w.match_keywords(
            "Ищу работу Python-разработчиком, вот мой контакт: ...",
            ["python"],
            [],
        )
        == []
    )
    assert (
        w.match_keywords(
            "Резюме: Python developer, 3 года опыта", ["python"], []
        )
        == []
    )
    assert w.match_keywords(
        "Ищем Python backend-разработчика в команду", ["python"], []
    ) == ["python"]


def test_match_keywords_rejects_resume_hashtags_but_keeps_vacancies():
    """Резюме в каналах помечают хэштегами; слово «резюме»/CV в самой
    вакансии («присылайте резюме») пост не отсекает."""
    for resume in (
        "#резюме #python #backend Обо мне: 4 года",
        "#cv #ищуработу Python Developer",
        "#Python #FastAPI #OpenToWork Junior Python",
    ):
        assert w.match_keywords(resume, ["python"], []) == []
    for vacancy in (
        "#вакансия Python-разработчик. Присылайте резюме на hr@acme.io",
        "#vacancy Python Developer, send your CV to jobs@acme.io",
    ):
        assert w.match_keywords(vacancy, ["python"], []) == ["python"]


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


class _FakeConnectingClient:
    """Клиент, который проверяет, что _SESSION_LOCK реально держится
    на всём connect()+_subscribe() — воспроизводит гонку из бага
    "database is locked" (search_telegram открывал вторую сессию,
    пока шлюз ещё подключался, потому что active_watcher() отдавал
    его только после self.connected=True)."""

    def __init__(self, lock_states: list):
        self.lock_states = lock_states

    async def connect(self):
        self.lock_states.append(("connect", _SESSION_LOCK.locked()))

    def remove_event_handler(self, *a, **k):
        pass

    async def is_user_authorized(self):
        return True

    def add_event_handler(self, *a, **k):
        pass

    async def run_until_disconnected(self):
        pass


def test_serve_holds_session_lock_through_connect_and_subscribe():
    with tempfile.TemporaryDirectory() as tmp:
        watcher = w.TelegramWatcher(
            1,
            "h",
            Path(tmp) / "s",
            ["geekjobs"],
            ["python"],
            [],
            "me",
            {"outputFileDirectory": Path(tmp), "dataFolder": Path(tmp)},
        )
        lock_states = []
        watcher.client = _FakeConnectingClient(lock_states)

        async def fake_subscribe():
            lock_states.append(("subscribe", _SESSION_LOCK.locked()))

        watcher._subscribe = fake_subscribe

        assert not _SESSION_LOCK.locked()
        asyncio.run(watcher._serve())
        assert not _SESSION_LOCK.locked()  # освобождён после подключения
        assert lock_states == [("connect", True), ("subscribe", True)]
        assert watcher.connected is True


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
        # Найденный в посте контакт — ещё не история обращения. В базу
        # он попадёт лишь после успешной отправки через кнопку/авторежим.
        assert ContactBook(Path(tmp)).all() == {}


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
        assert w._load_backfilled_channels(Path(tmp)) == {"geekjobs"}


def test_backfill_channel_is_not_marked_when_history_scan_fails():
    """Interrupted history scans must retry on the next watcher start."""
    from datetime import datetime, timezone

    history = [
        SimpleNamespace(
            message="Ищем Python-разработчика",
            id=10,
            date=datetime.now(timezone.utc),
        )
    ]
    with tempfile.TemporaryDirectory() as tmp:
        watcher = w.TelegramWatcher(
            1,
            "h",
            Path(tmp) / "s",
            ["geekjobs"],
            ["python"],
            [],
            "me",
            {
                "outputFileDirectory": Path(tmp),
                "dataFolder": Path(tmp),
                "telegram": {"channel_backfill_days": 14},
            },
        )
        watcher.client = _FakeClient(history=history)

        async def interrupted(*args):
            raise ConnectionError("connection lost")

        watcher._handle_post = interrupted
        asyncio.run(watcher._backfill_channel(object(), "geekjobs"))

        assert w._load_backfilled_channels(Path(tmp)) == set()


def test_disabled_backfill_clears_in_progress_channel():
    """Setting the history window to zero must not block a later retry."""
    with tempfile.TemporaryDirectory() as tmp:
        watcher = w.TelegramWatcher(
            1,
            "h",
            Path(tmp) / "s",
            ["geekjobs"],
            ["python"],
            [],
            "me",
            {
                "outputFileDirectory": Path(tmp),
                "dataFolder": Path(tmp),
                "telegram": {"channel_backfill_days": 0},
            },
        )
        watcher._backfills_in_progress.add("geekjobs")

        asyncio.run(watcher._backfill_channel(object(), "geekjobs"))

        assert watcher._backfills_in_progress == set()


def test_subscribe_does_not_start_duplicate_backfill_while_one_is_running():
    class SubscribeClient:
        async def get_entity(self, channel):
            return SimpleNamespace(left=False)

        def remove_event_handler(self, *args):
            pass

        def add_event_handler(self, *args):
            pass

    with tempfile.TemporaryDirectory() as tmp:
        watcher = w.TelegramWatcher(
            1,
            "h",
            Path(tmp) / "s",
            ["geekjobs"],
            ["python"],
            [],
            "me",
            {
                "outputFileDirectory": Path(tmp),
                "dataFolder": Path(tmp),
                "telegram": {"channel_backfill_days": 7},
            },
        )
        watcher.client = SubscribeClient()
        calls = []
        release = [None]

        async def slow_backfill(entity, channel):
            calls.append(channel)
            await release[0].wait()
            watcher._backfills_in_progress.discard(channel)

        watcher._backfill_channel = slow_backfill

        async def subscribe_twice():
            release[0] = asyncio.Event()
            await watcher._subscribe()
            await watcher._subscribe()
            await asyncio.sleep(0)
            assert calls == ["geekjobs"]
            release[0].set()
            await asyncio.sleep(0)

        asyncio.run(subscribe_twice())


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


def test_source_client_rechecks_watcher_after_waiting_for_session_lock(
    monkeypatch,
):
    """Пока клиент ждал сессионный замок, watcher мог подключиться.
    Тогда нельзя открывать второй Telethon-клиент."""
    watcher = SimpleNamespace(connected=True)
    checks = iter([None, watcher])
    starts = []
    source_client = object.__new__(TelegramSourceClient)
    source_client._watcher = None
    source_client._client = SimpleNamespace(start=lambda: starts.append(True))
    monkeypatch.setattr(w, "active_watcher", lambda: next(checks))

    assert source_client.__enter__() is source_client
    assert source_client._watcher is watcher
    assert starts == []
    assert not _SESSION_LOCK.locked()


def test_watch_settings_api(client):  # noqa: F811
    snap = client.get("/api/settings/telegram-watch").json()
    assert snap["enabled"] is False and snap["running"] is False
    # Встроенные стоп-слова видны в UI полным списком, не «и похожие».
    assert "ищу работу" in snap["builtin_stop_words"]
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


def test_watch_settings_api_updates_active_llm_filter(
    client, monkeypatch  # noqa: F811
):
    updates = []

    class _Watcher:
        connected = True
        matched_count = 0

        def update_llm_vacancy_filter(self, enabled):
            updates.append(enabled)

    monkeypatch.setattr(w, "_ACTIVE", _Watcher())

    response = client.post(
        "/api/settings/telegram-watch",
        json={"llm_vacancy_filter": True},
    )

    assert response.status_code == 200
    assert response.json()["llm_vacancy_filter"] is True
    assert updates == [True]


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
        [card] = ContactBook(params["outputFileDirectory"]).all().values()
        assert card["contacts"][0]["value"] == "anna_hr"
        assert card["contacts"][0]["source"] == "отклик на пост в @geekjobs"


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
        [card] = ContactBook(params["outputFileDirectory"]).all().values()
        assert card["contacts"][0]["source"] == "отклик на пост в @geekjobs"
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


def test_bot_delivery_routes_into_topic_when_available(monkeypatch):
    """Найденные вакансии от Telegram-парсера — самый шумный источник
    уведомлений (до 50 каналов) — должны уходить в свою тему
    "Telegram-каналы", если чат назначения это поддерживает."""
    with tempfile.TemporaryDirectory() as tmp:
        sent = []
        monkeypatch.setattr(
            w,
            "bot_request",
            lambda token, method, payload: sent.append(payload) or {},
        )
        monkeypatch.setattr(
            w, "get_or_create_topic", lambda parameters, category: 99
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
        assert payload["message_thread_id"] == 99


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


def test_watch_settings_refreshes_llm_vacancy_filter_without_restart(
    tmp_path, monkeypatch
):
    (tmp_path / "work_preferences.yaml").write_text(
        "telegram:\n  llm_vacancy_filter: true\n",
        encoding="utf-8",
    )
    watcher = w.TelegramWatcher(
        1,
        "h",
        tmp_path / "s",
        [],
        [],
        [],
        "me",
        {
            "outputFileDirectory": tmp_path,
            "dataFolder": tmp_path,
            "secretsFile": tmp_path / "x",
            "telegram": {"llm_vacancy_filter": False},
        },
    )
    connected = iter([True, False])
    watcher.client = SimpleNamespace(is_connected=lambda: next(connected))

    async def no_sleep(_):
        pass

    monkeypatch.setattr(w.asyncio, "sleep", no_sleep)
    asyncio.run(watcher._watch_settings())

    assert watcher.parameters["telegram"]["llm_vacancy_filter"] is True


def test_watch_settings_keeps_llm_filter_when_preference_is_missing(
    tmp_path, monkeypatch
):
    (tmp_path / "work_preferences.yaml").write_text(
        "telegram: {}\n",
        encoding="utf-8",
    )
    watcher = w.TelegramWatcher(
        1,
        "h",
        tmp_path / "s",
        [],
        [],
        [],
        "me",
        {
            "outputFileDirectory": tmp_path,
            "dataFolder": tmp_path,
            "secretsFile": tmp_path / "x",
            "telegram": {"llm_vacancy_filter": True},
        },
    )
    connected = iter([True, False])
    watcher.client = SimpleNamespace(is_connected=lambda: next(connected))

    async def no_sleep(_):
        pass

    monkeypatch.setattr(w.asyncio, "sleep", no_sleep)
    asyncio.run(watcher._watch_settings())

    assert watcher.parameters["telegram"]["llm_vacancy_filter"] is True


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
        monkeypatch.setattr(main, "notify", lambda *a, **k: None)
        main._check_contact_book_mail(params, {})
        assert status() == "replied"

        main._handle_vacancy_button(params, "key", "T", cb(f"n:{post_id}"))
        assert ContactBook(out).get("acme")["do_not_contact"] is True


def test_llm_check_post_picks_apply_email_by_rule(monkeypatch):
    """ИИ отвечает только «вакансия?»; адрес — правилом из поста: подпись
    канала «Размещение вакансий: ads@…» не адрес для отклика, даже если
    стоит первой; адреса, которого нет в посте, не бывает."""
    prompts, answers = [], iter(["ДА", "**ДА**", "НЕТ"])

    class _FakeLLM:
        def invoke(self, prompt):
            prompts.append(prompt)
            return SimpleNamespace(content=next(answers))

    monkeypatch.setattr(
        "src.job_sources.llm_provider.get_chat_llm",
        lambda *a, **kw: _FakeLLM(),
    )
    text = "Python Dev. Контакты: hr@acme.io\nРазмещение вакансий: ads@ch.ru"
    emails = ["ads@ch.ru", "hr@acme.io"]
    assert w._llm_check_post(text, "key", emails) == (True, "hr@acme.io")
    footer_only = "Python Dev\nРазмещение вакансий: ads@ch.ru"
    assert w._llm_check_post(footer_only, "key", ["ads@ch.ru"]) == (True, "")
    assert w._llm_check_post(text, "key", emails) == (False, "")
    assert "ДА или НЕТ" in prompts[0]


def _llm_watcher(tmp, telegram):
    watcher = w.TelegramWatcher(
        1,
        "h",
        Path(tmp) / "s",
        ["geekjobs"],
        ["python"],
        [],
        "me",
        {
            "outputFileDirectory": Path(tmp),
            "dataFolder": Path(tmp),
            "telegram": {"llm_vacancy_filter": True, **telegram},
        },
    )
    watcher.bot = ("T", "42")
    watcher.client = _FakeClient()
    return watcher


def test_verified_post_saves_only_apply_email_to_base(monkeypatch):
    """Проверенная вакансия: email для отклика — сразу в Базу (как адреса
    с сайтов компаний), @username — только после отправки из бота."""
    monkeypatch.setattr(
        w, "_llm_check_post", lambda text, key, emails: (True, "hr@acme.io")
    )
    monkeypatch.setattr(w, "bot_request", lambda *a: {})
    with tempfile.TemporaryDirectory() as tmp:
        watcher = _llm_watcher(tmp, {})
        asyncio.run(
            watcher._on_channel_post(
                _event("Python Dev в Acme: hr@acme.io, вопросы @anna_hr")
            )
        )
        [card] = ContactBook(Path(tmp)).all().values()
    assert [(c["value"], c["source"]) for c in card["contacts"]] == [
        ("hr@acme.io", "пост в @geekjobs")
    ]


def test_unverified_post_reaches_bot_without_auto_send_or_base(monkeypatch):
    """ИИ недоступен: пост не теряется (в бот с пометкой), но ничего
    автоматического — ни автоотправки, ни Базы, ни вердикта каналу."""
    monkeypatch.setattr(w, "_llm_check_post", lambda *a: None)
    sent = []
    monkeypatch.setattr(
        w, "bot_request", lambda token, method, payload: sent.append(payload)
    )
    with tempfile.TemporaryDirectory() as tmp:
        watcher = _llm_watcher(tmp, {"auto_message": True})
        asyncio.run(
            watcher._on_channel_post(
                _event("Python Dev в Acme: hr@acme.io, пишите @anna_hr")
            )
        )
        assert w.pending_telegram_sends_count(Path(tmp)) == 0
        assert ContactBook(Path(tmp)).all() == {}
    [payload] = sent
    assert "⚠️ не проверено ИИ" in payload["text"]


def test_buttons_mark_contacts_already_written_or_queued():
    from datetime import datetime

    from src.direct.campaign import CampaignStore

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        TelegramConversations(
            out / "telegram_conversations.json"
        ).record_outbound("anna_hr", "Здравствуйте")
        CampaignStore(out).create(
            "all", [{"key": "acme", "email": "hr@acme.io", "company": "Acme"}]
        )
        contacts = [
            {"kind": "telegram", "value": "Anna_HR"},
            {"kind": "email", "value": "HR@acme.io"},
        ]
        notes = w.contact_notes(out, contacts)
    written = f"писали {datetime.now().astimezone():%d.%m}"
    assert notes == {"anna_hr": written, "hr@acme.io": "в очереди рассылки"}
    rows = w.vacancy_keyboard("abc", contacts, [], notes)["inline_keyboard"]
    assert rows[0][0]["text"] == f"👋 @Anna_HR · {written}"
    assert rows[2][0]["text"].endswith("(LLM) · в очереди рассылки")


def test_do_not_write_creates_card_for_post_contact(monkeypatch):
    """Контакт поста ещё не в Базе (ему не писали) — «Не писать компании»
    всё равно срабатывает: заводит карточку сразу со статусом."""
    with tempfile.TemporaryDirectory() as tmp:
        main, params, post_id, calls, cb = _button_env(tmp, monkeypatch)
        main._handle_vacancy_button(params, "key", "T", cb(f"n:{post_id}"))
        [card] = ContactBook(params["outputFileDirectory"]).all().values()
    assert card["do_not_contact"] is True
    assert card["contacts"][0]["source"] == "пост в @geekjobs"


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
        remembered = []
        w.flush_pending_telegram_sends(
            lambda contact, text: sent.append((contact, text)),
            out,
            None,
            on_sent=lambda entry: remembered.append(entry["contact"]),
        )
        assert sent == [("hr_user", "текст письма")]
        assert remembered == ["hr_user"]


def test_pending_telegram_send_attaches_resume_file_after_text():
    """resume_path в очереди — файл резюме уходит send_file_fn сразу
    после текста, без ссылки в самом сообщении; без send_file_fn или
    без resume_path файл не отправляется."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        w.queue_telegram_send(
            out,
            "hr_user",
            "текст письма",
            "https://t.me/c/1",
            0,
            0,
            resume_path="/tmp/resume.pdf",
        )
        sent_files = []
        w.flush_pending_telegram_sends(
            lambda contact, text: None,
            out,
            None,
            send_file_fn=lambda contact, path: sent_files.append(
                (contact, path)
            ),
        )
        assert sent_files == [("hr_user", "/tmp/resume.pdf")]

        # Без resume_path (обычное сообщение) — файл не пытаемся слать.
        w.queue_telegram_send(
            out, "other_user", "другой текст", "https://t.me/c/2", 0, 0
        )
        w.flush_pending_telegram_sends(
            lambda contact, text: None,
            out,
            None,
            send_file_fn=lambda contact, path: sent_files.append(
                (contact, path)
            ),
        )
        assert sent_files == [("hr_user", "/tmp/resume.pdf")]
        assert w.pending_telegram_sends_count(out) == 0


def test_call_runs_sync_style_client_method_inside_gateway_loop():
    """8.10: telethon.sync делает методы клиента синхронными вне
    запущенного loop — вызванный в потоке вызывающего, c.get_entity()
    шёл в чужой loop («event loop must not change after connection»).
    call() должен вызывать его уже внутри loop шлюза."""
    import asyncio
    import threading

    from telethon import helpers

    from src.job_sources.telegram.watcher import TelegramWatcher

    class FakeClient:
        async def _get(self, name):
            return name, asyncio.get_running_loop()

        def get_entity(self, name):  # как у telethon.sync
            coro = self._get(name)
            loop = helpers.get_running_loop()
            return coro if loop.is_running() else loop.run_until_complete(coro)

    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()
    try:
        watcher = TelegramWatcher.__new__(TelegramWatcher)
        watcher.loop, watcher.client = loop, FakeClient()
        name, used_loop = watcher.call(lambda c: c.get_entity("chan"))
        assert name == "chan" and used_loop is loop
    finally:
        loop.call_soon_threadsafe(loop.stop)
