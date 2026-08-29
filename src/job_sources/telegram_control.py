from __future__ import annotations

import json
import re
from pathlib import Path

import httpx

from src.job_sources.telegram_notify import TELEGRAM_API_BASE

_OFFSET_FILE = ".telegram_control_offset.json"

_STATUS_RE = re.compile(r"^/status\s*$", re.IGNORECASE)
_PAUSE_RE = re.compile(r"^/pause\s+(\w+)\s*$", re.IGNORECASE)
_RESUME_RE = re.compile(r"^/resume\s+(\w+)\s*$", re.IGNORECASE)
_HELP_RE = re.compile(r"^/(help|start)\s*$", re.IGNORECASE)

HELP_TEXT = (
    "Команды:\n"
    "/status — статус всех площадок за сегодня\n"
    "/pause <площадка> — снять площадку с расписания демона\n"
    "/resume <площадка> — вернуть площадку в расписание"
)


def _offset_path(output_folder: Path) -> Path:
    return output_folder / _OFFSET_FILE


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def poll_control_commands(
    bot_token: str, chat_id: str, output_folder: Path
) -> list[dict]:
    """Тот же приём опроса getUpdates, что
    headhunter.telegram_approval.poll_form_commands — свой offset-файл
    (не пересекается с очередью подтверждения анкет), команды
    удалённого управления демоном вместо подтверждения форм.
    Возвращает {"action": "status"|"help"|"pause"|"resume", "source": ...}."""
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

        if _STATUS_RE.match(text):
            commands.append({"action": "status"})
            continue
        if _HELP_RE.match(text):
            commands.append({"action": "help"})
            continue
        match = _PAUSE_RE.match(text)
        if match:
            commands.append({"action": "pause", "source": match.group(1).lower()})
            continue
        match = _RESUME_RE.match(text)
        if match:
            commands.append({"action": "resume", "source": match.group(1).lower()})
            continue

    if updates:
        _offset_path(output_folder).write_text(
            json.dumps({"offset": max_update_id + 1}), encoding="utf-8"
        )
    return commands
