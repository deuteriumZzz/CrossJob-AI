from __future__ import annotations

import json
import re
import secrets
import time
from pathlib import Path

import httpx
import yaml

from src.job_sources.telegram_notify import (
    TELEGRAM_API_BASE,
    send_notification,
)
from src.logging import logger

_PENDING_FILE = ".pending_form_confirmations.json"
_OFFSET_FILE = ".telegram_updates_offset.json"
_APPROVE_RE = re.compile(
    r"^(?:да|yes|ок|ok)\s+([a-z0-9]{4})\s*$", re.IGNORECASE
)
_REGENERATE_RE = re.compile(
    r"^(?:заново|regenerate)\s+([a-z0-9]{4})\s*$", re.IGNORECASE
)
_EDIT_RE = re.compile(
    r"^(?:правка|edit)\s+([a-z0-9]{4})\s+(\d+)\s+(.+)$",
    re.IGNORECASE | re.DOTALL,
)


def _pending_path(output_folder: Path) -> Path:
    return output_folder / _PENDING_FILE


def _offset_path(output_folder: Path) -> Path:
    return output_folder / _OFFSET_FILE


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_pending_form(
    output_folder: Path,
    company: str,
    title: str,
    form_url: str,
    external_id: str,
    questions: list[dict],
    answers: list[dict],
) -> str:
    """Записывает форму, ждущую подтверждения в Telegram — короткий id
    (4 hex-символа) вместо длинного, чтобы ответить одним словом было
    удобно с телефона: "да a1b2". questions/answers (уже сериализо-
    ванные form_fill.questions_to_dicts/answers_to_dicts) сохраняются
    целиком, чтобы при подтверждении форма заполнялась ровно тем, что
    было показано пользователю — без повторного LLM-вызова и риска,
    что черновик "уедет" между показом и заполнением."""
    pending = _load_json(_pending_path(output_folder))
    form_id = secrets.token_hex(2)
    pending[form_id] = {
        "company": company,
        "title": title,
        "form_url": form_url,
        "external_id": external_id,
        "questions": questions,
        "answers": answers,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    _pending_path(output_folder).write_text(
        json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return form_id


def get_pending_form(output_folder: Path, form_id: str) -> dict | None:
    return _load_json(_pending_path(output_folder)).get(form_id)


def update_pending_form_answers(
    output_folder: Path, form_id: str, answers: list[dict]
) -> dict | None:
    """Перезаписывает answers у уже сохранённой формы (правка одного
    пункта или полная перегенерация) — questions/company/title/
    form_url/external_id не трогает. Возвращает обновлённую запись,
    или None если form_id уже не существует (например, устарел)."""
    pending = _load_json(_pending_path(output_folder))
    if form_id not in pending:
        return None
    pending[form_id]["answers"] = answers
    _pending_path(output_folder).write_text(
        json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return pending[form_id]


def remove_pending_form(output_folder: Path, form_id: str) -> None:
    pending = _load_json(_pending_path(output_folder))
    pending.pop(form_id, None)
    _pending_path(output_folder).write_text(
        json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def poll_form_commands(
    bot_token: str, chat_id: str, output_folder: Path
) -> list[dict]:
    """Опрашивает getUpdates (обычный Bot API, как и send_notification
    — не Telethon) на новые сообщения-команды в нужном чате, начиная
    с сохранённого offset, чтобы не обрабатывать одно и то же
    сообщение дважды между прогонами:
    - "да <id>" / "yes <id>" — подтвердить как есть и отправить.
    - "заново <id>" — перегенерировать черновик заново.
    - "правка <id> <номер вопроса> <новый ответ>" — точечно
      исправить один ответ, без похода по ссылке.
    Возвращает список {"action": ..., "form_id": ..., ...}; сам файл
    ожидания не трогает — вызывающий код решает, что делать."""
    offset_data = _load_json(_offset_path(output_folder))
    offset = offset_data.get("offset", 0)

    response = httpx.get(
        f"{TELEGRAM_API_BASE}/bot{bot_token}/getUpdates",
        params={"offset": offset, "timeout": 0},
        timeout=10,
    )
    response.raise_for_status()
    updates = response.json().get("result", [])

    commands = []
    max_update_id = offset - 1
    for update in updates:
        max_update_id = max(max_update_id, update.get("update_id", 0))
        message = update.get("message") or {}
        if str(message.get("chat", {}).get("id")) != str(chat_id):
            continue
        text = (message.get("text") or "").strip()

        match = _APPROVE_RE.match(text)
        if match:
            commands.append({"action": "approve", "form_id": match.group(1)})
            continue

        match = _REGENERATE_RE.match(text)
        if match:
            commands.append(
                {"action": "regenerate", "form_id": match.group(1)}
            )
            continue

        match = _EDIT_RE.match(text)
        if match:
            commands.append(
                {
                    "action": "edit",
                    "form_id": match.group(1),
                    "question_index": int(match.group(2)),
                    "new_text": match.group(3).strip(),
                }
            )
            continue

    if updates:
        _offset_path(output_folder).write_text(
            json.dumps({"offset": max_update_id + 1}), encoding="utf-8"
        )
    return commands


def notify_pending_form(
    parameters: dict,
    form_id: str,
    company: str,
    title: str,
    form_url: str,
    questions_and_answers: str,
    is_update: bool = False,
) -> None:
    heading = (
        "Обновлённый черновик анкеты"
        if is_update
        else "Работодатель просит заполнить анкету"
    )
    text = (
        f"{heading}: {company} — {title}\n"
        f"{form_url}\n\n"
        f"Черновик ответов:\n{questions_and_answers}\n\n"
        f'Отправить как есть — "да {form_id}"\n'
        f'Перегенерировать заново — "заново {form_id}"\n'
        f'Поправить один пункт — "правка {form_id} <номер вопроса> '
        f'<новый ответ>"'
    )
    secrets_file = parameters["secretsFile"]
    with open(secrets_file, "r") as stream:
        secrets_yaml = yaml.safe_load(stream) or {}
    notifications = secrets_yaml.get("notifications") or {}
    bot_token = notifications.get("telegram_bot_token")
    chat_id = notifications.get("telegram_chat_id")
    if not bot_token or not chat_id:
        logger.warning(
            "notifications.telegram_bot_token/chat_id not set — "
            "cannot ask for form-fill approval, skipping."
        )
        return
    try:
        send_notification(bot_token, chat_id, text)
    except Exception as e:
        logger.warning(f"Failed to send form-approval Telegram message: {e}")
