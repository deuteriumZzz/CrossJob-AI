from pathlib import Path

from typing import Optional

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


def send_document_from_secrets(
    parameters: dict, filename: str, content: bytes, caption: str
) -> None:
    """Файл в тот же Telegram-бот (например .ics приглашения на
    интервью — одно нажатие добавляет событие в календарь). Best-effort,
    как notify_from_secrets."""
    try:
        with open(parameters["secretsFile"], "r") as stream:
            secrets = yaml.safe_load(stream) or {}
        notifications = secrets.get("notifications") or {}
        bot_token = notifications.get("telegram_bot_token")
        chat_id = notifications.get("telegram_chat_id")
        if not bot_token or not chat_id:
            return
        response = httpx.post(
            f"{TELEGRAM_API_BASE}/bot{bot_token}/sendDocument",
            data={"chat_id": chat_id, "caption": caption},
            files={"document": (filename, content)},
            timeout=20,
        )
        response.raise_for_status()
    except Exception as e:
        logger.warning(f"Failed to send Telegram document: {e}")


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


def bot_request(bot_token: str, method: str, payload: dict) -> dict:
    """Любой метод Bot API (sendMessage с кнопками, answerCallbackQuery,
    editMessageReplyMarkup…). Бросает при ошибке — вызывающий решает."""
    response = httpx.post(
        f"{TELEGRAM_API_BASE}/bot{bot_token}/{method}", json=payload, timeout=15
    )
    response.raise_for_status()
    return response.json().get("result") or {}


def bot_credentials(parameters: dict) -> "Optional[tuple[str, str]]":
    """(bot_token, chat_id) бота уведомлений из secrets.yaml или None."""
    try:
        with open(parameters["secretsFile"], "r") as stream:
            secrets = yaml.safe_load(stream) or {}
    except (OSError, KeyError):
        return None
    notifications = secrets.get("notifications") or {}
    token, chat_id = (
        notifications.get("telegram_bot_token"),
        notifications.get("telegram_chat_id"),
    )
    return (token, str(chat_id)) if token and chat_id else None
