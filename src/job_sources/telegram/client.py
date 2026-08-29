import asyncio
import threading
from pathlib import Path

# telethon.sync (не просто telethon!) — иначе TelegramClient остаётся
# чисто async, и любой синхронный вызов метода (is_user_authorized(),
# send_message(), sign_in()...) молча возвращает неисполненную
# корутину вместо результата (у .start() есть отдельная встроенная
# self-driving логика, поэтому раньше "работало" только в объёме
# TelegramSourceClient.__enter__). Импорт telethon.sync патчит методы
# класса TelegramClient — но НЕ его __init__ (syncify() пропускает
# приватные имена), поэтому конструктор всё ещё падает без event loop
# в текущем потоке — см. _ensure_event_loop() ниже, вызывается
# отдельно перед каждым TelegramClient(...).
from telethon.sync import TelegramClient
from telethon.tl.custom.message import Message


def _ensure_event_loop() -> None:
    """TelegramClient.__init__ вызывает asyncio.Lock(), а тот —
    asyncio.get_event_loop() напрямую (не через telethon's
    syncify-обёртку, которая пропускает __init__) — в потоке без
    когда-либо заведённого event loop'а (FastAPI-воркер, поток
    демона) это падает с "There is no current event loop". Вызывать
    перед конструированием TelegramClient из любого не главного
    потока."""
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())


# Один файл сессии (SQLite) не рассчитан на параллельный доступ сразу из
# нескольких клиентов — а в вебui это реально происходит: демон может в
# этот момент читать каналы, пока пользователь открывает статус
# подключения или пишет сообщение из чата. Простой process-wide лок
# вместо очереди задач: сериализует все обращения к Telegram ценой
# ожидания при наложении операций друг на друга.
# ponytail: один общий лок на всё вместо очереди/пула соединений —
# апгрейд, если задержки от последовательного доступа станут заметны.
_SESSION_LOCK = threading.Lock()


def normalize_channel(raw: str) -> str:
    """@username, голый username и полная ссылка (https://t.me/username,
    t.me/username) — приводим к тому виду, который принимает Telethon
    (голый username), чтобы в work_preferences.yaml можно было вставлять
    то, что реально скопировано из Telegram."""
    value = raw.strip()
    for prefix in ("https://t.me/", "http://t.me/", "t.me/", "@"):
        if value.lower().startswith(prefix):
            value = value[len(prefix) :]
            break
    return value.split("/")[0].strip()


class TelegramSourceClient:
    """Обёртка над сессией Telethon. Первый запуск требует
    интерактивного ввода номера телефона + кода входа (и пароля 2FA,
    если включена) в консоли; файл сессии избавляет от этого при
    следующих запусках."""

    def __init__(self, api_id: int, api_hash: str, session_path: Path):
        session_path.parent.mkdir(parents=True, exist_ok=True)
        _ensure_event_loop()
        self._client = TelegramClient(str(session_path), api_id, api_hash)

    def __enter__(self) -> "TelegramSourceClient":
        _SESSION_LOCK.acquire()
        self._client.start()
        return self

    def __exit__(self, *exc_info) -> None:
        self._client.disconnect()
        _SESSION_LOCK.release()

    def iter_channel_messages(self, channel: str, limit: int) -> list[Message]:
        return list(self._client.iter_messages(channel, limit=limit))

    def send_message(self, contact: str, text: str) -> Message:
        return self._client.send_message(contact, text)

    def send_file(
        self, contact: str, file_path: Path, caption: str = ""
    ) -> Message:
        return self._client.send_file(contact, str(file_path), caption=caption)

    def new_incoming_messages(
        self, contact: str, min_id: int
    ) -> list[Message]:
        """Сообщения от contact'а после min_id (0 — вся история), новые
        первыми. Личный диалог содержит и наши исходящие, и его
        входящие — оставляем только входящие (m.out is False)."""
        return [
            m
            for m in self._client.iter_messages(contact, min_id=min_id)
            if not m.out
        ]


class TelegramStatusClient:
    """Отдельный тонкий контекст-менеджер для проверки статуса сессии
    без интерактивного логина: connect() (в отличие от start() у
    TelegramSourceClient) ничего не спрашивает в консоли, если сессия
    не авторизована — просто даёт is_user_authorized() вернуть False.
    Нужен отдельным классом, а не флагом на TelegramSourceClient,
    потому что вызывается из вебui-запроса, где интерактивный ввод
    физически негде показать."""

    def __init__(self, api_id: int, api_hash: str, session_path: Path):
        session_path.parent.mkdir(parents=True, exist_ok=True)
        _ensure_event_loop()
        self._client = TelegramClient(str(session_path), api_id, api_hash)

    def __enter__(self) -> "TelegramStatusClient":
        _SESSION_LOCK.acquire()
        self._client.connect()
        return self

    def __exit__(self, *exc_info) -> None:
        self._client.disconnect()
        _SESSION_LOCK.release()

    def is_authorized(self) -> bool:
        return self._client.is_user_authorized()


class TelegramLoginSession:
    """Многошаговый вход из вебui вместо интерактивного консольного —
    обычному пользователю неоткуда набрать код в терминале приложения.
    send_code()/submit_code()/submit_password() должны идти на ОДНОМ и
    том же экземпляре между HTTP-запросами (Telethon хранит
    phone_code_hash на самом клиенте) — вызывающий код (вебui) держит
    один такой объект в AppContext, пока пользователь не пройдёт все
    шаги или не отменит.
    ponytail: не берёт _SESSION_LOCK — это одноразовое ручное действие
    пользователя, а не горячий путь; апгрейд, если демон и вход из
    вебui реально столкнутся на одной сессии одновременно."""

    def __init__(self, api_id: int, api_hash: str, session_path: Path):
        session_path.parent.mkdir(parents=True, exist_ok=True)
        _ensure_event_loop()
        self._client = TelegramClient(str(session_path), api_id, api_hash)
        self._phone: str = ""
        self._client.connect()

    def send_code(self, phone: str) -> None:
        self._phone = phone
        self._client.send_code_request(phone)

    def submit_code(self, code: str) -> bool:
        """True — вошли сразу; False — включена 2FA, нужен
        submit_password()."""
        from telethon.errors import SessionPasswordNeededError

        try:
            self._client.sign_in(phone=self._phone, code=code)
            return True
        except SessionPasswordNeededError:
            return False

    def submit_password(self, password: str) -> None:
        self._client.sign_in(password=password)

    def close(self) -> None:
        self._client.disconnect()
