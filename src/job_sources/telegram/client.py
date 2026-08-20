from pathlib import Path

from telethon import TelegramClient
from telethon.tl.custom.message import Message


class TelegramSourceClient:
    """Обёртка над сессией Telethon. Первый запуск требует
    интерактивного ввода номера телефона + кода входа (и пароля 2FA,
    если включена) в консоли; файл сессии избавляет от этого при
    следующих запусках."""

    def __init__(self, api_id: int, api_hash: str, session_path: Path):
        session_path.parent.mkdir(parents=True, exist_ok=True)
        self._client = TelegramClient(str(session_path), api_id, api_hash)

    def __enter__(self) -> "TelegramSourceClient":
        self._client.start()
        return self

    def __exit__(self, *exc_info) -> None:
        self._client.disconnect()

    def iter_channel_messages(self, channel: str, limit: int) -> list[Message]:
        return list(self._client.iter_messages(channel, limit=limit))
