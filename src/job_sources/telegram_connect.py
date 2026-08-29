from __future__ import annotations

import time
from typing import Optional

import httpx

from src.job_sources.telegram_notify import TELEGRAM_API_BASE


def get_bot_username(bot_token: str) -> str:
    """getMe — заодно служит проверкой, что токен вообще валиден,
    прежде чем сохранять его и показывать deep-link на несуществующего
    бота."""
    response = httpx.get(
        f"{TELEGRAM_API_BASE}/bot{bot_token}/getMe", timeout=10
    )
    response.raise_for_status()
    return response.json()["result"]["username"]


def wait_for_start(
    bot_token: str, timeout_seconds: int = 180
) -> Optional[str]:
    """Поллит getUpdates (long-polling, timeout прямо в запросе — не
    долбит API раз в секунду) в ожидании /start от пользователя, чтобы
    достать chat_id автоматически — замена ручному походу на
    getUpdates в браузере и копипасте id из JSON (как раньше требовала
    инструкция в index.html). Возвращает None, если /start не пришёл
    за timeout_seconds."""
    deadline = time.monotonic() + timeout_seconds
    offset = 0
    while time.monotonic() < deadline:
        remaining = max(1, int(deadline - time.monotonic()))
        poll_timeout = min(25, remaining)
        try:
            response = httpx.get(
                f"{TELEGRAM_API_BASE}/bot{bot_token}/getUpdates",
                params={"offset": offset, "timeout": poll_timeout},
                timeout=poll_timeout + 10,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            time.sleep(2)
            continue
        for update in response.json().get("result", []):
            offset = max(offset, update.get("update_id", 0) + 1)
            message = update.get("message") or {}
            text = (message.get("text") or "").strip()
            if text.startswith("/start"):
                return str(message["chat"]["id"])
    return None
