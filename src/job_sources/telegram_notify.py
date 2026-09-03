from pathlib import Path

import httpx
import yaml

from src.logging import logger

TELEGRAM_API_BASE = "https://api.telegram.org"


def notify_manual_login_required(
    parameters: dict, source_name: str, timeout_seconds: int
) -> None:
    """Шлём сразу, как только открылось окно ручного входа — иначе
    уведомление о сбое приходит только после timeout_seconds, когда
    окно логина уже закрыто (driver.quit()) и реагировать поздно."""
    notify_from_secrets(
        parameters,
        f"CrossJob-AI: {source_name} требует ручного входа — "
        f"откройте Chrome в течение {timeout_seconds}с, "
        "иначе прогон сорвётся.",
    )


def notify_from_secrets(parameters: dict, text: str) -> None:
    """Best-effort уведомление в Telegram из parameters["secretsFile"]
    — общая реализация main.notify()/Scheduler, живёт здесь (а не в
    main.py), чтобы scheduler.py могла её импортировать без
    циклического импорта main.py <-> src.scheduler."""
    try:
        secrets_path: Path = parameters["secretsFile"]
        with open(secrets_path, "r") as stream:
            secrets = yaml.safe_load(stream) or {}
        notifications = secrets.get("notifications") or {}
        bot_token = notifications.get("telegram_bot_token")
        chat_id = notifications.get("telegram_chat_id")
        if not bot_token or not chat_id:
            return
        send_notification(bot_token, chat_id, text)
    except Exception as e:
        logger.warning(f"Failed to send Telegram notification: {e}")


def send_notification(bot_token: str, chat_id: str, text: str) -> None:
    """Прямой httpx.post вместо Telethon (юзер-сессия, нужна для
    чтения каналов в TelegramSourceClient) — для простого "уведомить
    себя" достаточно обычного бота через @BotFather, без входа под
    личным аккаунтом."""
    response = httpx.post(
        f"{TELEGRAM_API_BASE}/bot{bot_token}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=10,
    )
    response.raise_for_status()
