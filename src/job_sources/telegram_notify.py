import json
from pathlib import Path
from typing import Any, Optional

import httpx
import yaml

from src.logging import logger
from src.utils.file_lock import state_file_lock

TELEGRAM_API_BASE = "https://api.telegram.org"
TOPICS_CACHE_FILE = ".telegram_topics.json"


class TelegramAPIError(RuntimeError):
    """A Bot API error whose message never contains the bot token."""


def raise_for_telegram_status(response: httpx.Response, method: str) -> None:
    """Raise a sanitized error instead of httpx's token-bearing request URL."""
    try:
        response.raise_for_status()
    except Exception:
        description = ""
        try:
            payload = response.json()
            if isinstance(payload, dict):
                description = str(payload.get("description") or "")
        except Exception:
            pass
        status = getattr(response, "status_code", "error")
        detail = f": {description[:200]}" if description else ""
        raise TelegramAPIError(
            f"Telegram API {method} returned HTTP {status}{detail}"
        ) from None


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
        category=source_name,
    )


def _load_topics_cache(parameters: dict) -> "tuple[Path, dict]":
    path = Path(parameters["outputFileDirectory"]) / TOPICS_CACHE_FILE
    try:
        cache = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    return path, cache


def get_or_create_topic(parameters: dict, category: str) -> Optional[int]:
    """message_thread_id темы для category в группе-получателе
    уведомлений (см. TOPICS_CACHE_FILE) — по одной теме на площадку/
    категорию, чтобы не мешать всё в один чат "стеной текста". Если
    chat_id — не супергруппа с включёнными темами (обычный личный чат
    с ботом, как раньше) или бот не админ с правом "Управление
    темами" — createForumTopic вернёт ошибку, ловим её и отдаём None:
    вызывающий код тогда шлёт обычным сообщением без темы, ничего не
    ломая для тех, кто "папки" не настраивал."""
    creds = bot_credentials(parameters)
    if not creds:
        return None
    bot_token, chat_id = creds
    path, cache = _load_topics_cache(parameters)
    if category in cache:
        return cache[category]
    try:
        result = bot_request(
            bot_token,
            "createForumTopic",
            {"chat_id": chat_id, "name": category[:128]},
        )
        thread_id = result.get("message_thread_id")
    except Exception as e:
        logger.info(
            f"Telegram: не удалось создать тему '{category}' (обычный "
            f"чат без тем, или бот не админ) — шлю без темы: {e}"
        )
        return None
    if thread_id is None:
        return None
    with state_file_lock(path):
        _, cache = _load_topics_cache(parameters)
        cache[category] = thread_id
        path.write_text(json.dumps(cache, ensure_ascii=False), "utf-8")
    return thread_id


def notify_from_secrets(
    parameters: dict, text: str, category: Optional[str] = None
) -> None:
    """Best-effort уведомление в Telegram из parameters["secretsFile"]
    — общая реализация main.notify()/Scheduler, живёт здесь (а не в
    main.py), чтобы scheduler.py могла её импортировать без
    циклического импорта main.py <-> src.scheduler. category — имя
    темы (Avito, HeadHunter, Ошибки, ...), см. get_or_create_topic."""
    try:
        secrets_path: Path = parameters["secretsFile"]
        with open(secrets_path, "r") as stream:
            secrets = yaml.safe_load(stream) or {}
        notifications = secrets.get("notifications") or {}
        bot_token = notifications.get("telegram_bot_token")
        chat_id = notifications.get("telegram_chat_id")
        if not bot_token or not chat_id:
            return
        thread_id = (
            get_or_create_topic(parameters, category) if category else None
        )
        send_notification(bot_token, chat_id, text, thread_id)
    except Exception as e:
        logger.warning(f"Failed to send Telegram notification: {e}")


def send_document_from_secrets(
    parameters: dict,
    filename: str,
    content: bytes,
    caption: str,
    category: Optional[str] = None,
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
        thread_id = (
            get_or_create_topic(parameters, category) if category else None
        )
        data = {"chat_id": chat_id, "caption": caption}
        if thread_id is not None:
            data["message_thread_id"] = thread_id
        response = httpx.post(
            f"{TELEGRAM_API_BASE}/bot{bot_token}/sendDocument",
            data=data,
            files={"document": (filename, content)},
            timeout=20,
        )
        raise_for_telegram_status(response, "sendDocument")
    except Exception as e:
        logger.warning(f"Failed to send Telegram document: {e}")


def send_notification(
    bot_token: str,
    chat_id: str,
    text: str,
    message_thread_id: Optional[int] = None,
) -> None:
    """Прямой httpx.post вместо Telethon (юзер-сессия, нужна для
    чтения каналов в TelegramSourceClient) — для простого "уведомить
    себя" достаточно обычного бота через @BotFather, без входа под
    личным аккаунтом."""
    payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
    if message_thread_id is not None:
        payload["message_thread_id"] = message_thread_id
    response = httpx.post(
        f"{TELEGRAM_API_BASE}/bot{bot_token}/sendMessage",
        json=payload,
        timeout=10,
    )
    raise_for_telegram_status(response, "sendMessage")


def bot_request(bot_token: str, method: str, payload: dict) -> dict:
    """Любой метод Bot API (sendMessage с кнопками, answerCallbackQuery,
    editMessageReplyMarkup…). Бросает при ошибке — вызывающий решает."""
    response = httpx.post(
        f"{TELEGRAM_API_BASE}/bot{bot_token}/{method}",
        json=payload,
        timeout=15,
    )
    raise_for_telegram_status(response, method)
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
