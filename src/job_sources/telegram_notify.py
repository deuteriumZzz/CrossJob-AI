import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import httpx
import yaml

from src.logging import logger
from src.utils.file_lock import state_file_lock
from src.utils.shared_browser import reveal_shared_browser

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
    окно логина уже закрыто (driver.quit()) и реагировать поздно.
    Общий браузер свёрнут — здесь же показываем его для ручного входа."""
    reveal_shared_browser()
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
    темы (Avito, HeadHunter, Ошибки, ...), см. get_or_create_topic.

    Не ушло (Telegram недоступен) — не теряется: ложится в
    .pending_notifications.json и досылается перед следующим
    уведомлением, когда связь вернётся. Живой случай: час таймаутов до
    api.telegram.org, и сообщение «HH: капча» пропало молча."""
    try:
        secrets_path: Path = parameters["secretsFile"]
        with open(secrets_path, "r") as stream:
            secrets = yaml.safe_load(stream) or {}
        notifications = secrets.get("notifications") or {}
        bot_token = notifications.get("telegram_bot_token")
        chat_id = notifications.get("telegram_chat_id")
    except Exception as e:
        logger.warning(f"Failed to send Telegram notification: {e}")
        return
    if not bot_token or not chat_id:
        return
    output = parameters.get("outputFileDirectory")
    pending = Path(output) / _PENDING_FILE if output else None
    queue = _take_pending(pending) + [
        {"text": text, "category": category, "at": ""}
    ]
    sent = 0
    for item in queue:
        body = (
            f"⏳ {item['at']}, доставлено с опозданием:\n{item['text']}"
            if item["at"]
            else item["text"]
        )
        try:
            thread_id = (
                get_or_create_topic(parameters, item["category"])
                if item["category"]
                else None
            )
            send_notification(bot_token, chat_id, body, thread_id)
        except Exception as e:
            logger.warning(f"Failed to send Telegram notification: {e}")
            break
        sent += 1
    if pending is not None and sent < len(queue):
        now = datetime.now().strftime("%d.%m %H:%M")
        _put_pending(
            pending,
            [{**item, "at": item["at"] or now} for item in queue[sent:]],
        )


_PENDING_FILE = ".pending_notifications.json"
# ponytail: хвост последних 20 — после долгого обрыва не досылать сотню
# рутинных сообщений пачкой; поднять, если начнут теряться важные.
_PENDING_LIMIT = 20


def _take_pending(path: Optional[Path]) -> list[dict]:
    """Забирает отложенные уведомления (файл очищается под блокировкой,
    сама отправка — уже без неё, чтобы не держать блокировку на сети)."""
    if path is None or not path.exists():
        return []
    with state_file_lock(path):
        try:
            items = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            items = []
        path.write_text("[]", encoding="utf-8")
    return items if isinstance(items, list) else []


def _put_pending(path: Path, items: list[dict]) -> None:
    with state_file_lock(path):
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            current = []
        path.write_text(
            json.dumps(
                (current + items)[-_PENDING_LIMIT:], ensure_ascii=False
            ),
            encoding="utf-8",
        )


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
