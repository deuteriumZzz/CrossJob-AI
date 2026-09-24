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
# Короткие имена, которые люди пишут на самом деле.
_SOURCE_ALIASES = {"hh": "headhunter", "habr": "habr_career", "li": "linkedin", "gm": "getmatch", "tg": "telegram"}
_HELP_RE = re.compile(r"^/(help|start)\s*$", re.IGNORECASE)
_SEND_DRAFT_RE = re.compile(
    r"^(?:отправить|send)\s+([a-f0-9]{4})\s*$", re.IGNORECASE
)
_SKIP_DRAFT_RE = re.compile(
    r"^(?:пропустить|skip)\s+([a-f0-9]{4})\s*$", re.IGNORECASE
)

HELP_TEXT = (
    "Команды:\n"
    "/status — статус всех площадок за сегодня\n"
    "/pause <площадка> — поставить площадку на паузу (например, /pause hh)\n"
    "/resume <площадка> — снова включить (например, после капчи)\n"
    "отправить <код> / пропустить <код> — черновик ответа HR"
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


def poll_bot_updates(
    bot_token: str, output_folder: Path, timeout: int = 0
) -> list[dict]:
    """ЕДИНСТВЕННЫЙ читатель обновлений бота. Раньше команды и анкеты hh
    читали getUpdates каждый со своим offset-файлом — но Telegram,
    отдав обновления одному, помечает их прочитанными для всех, и
    «да <id>» для анкеты могло пропасть, если первым его забрал разбор
    /status. Теперь читаем здесь, а разбирают parse_* из одного списка.
    timeout>0 — long polling (постоянный шлюз: кнопки срабатывают сразу)."""
    offset = _load_json(_offset_path(output_folder)).get("offset", 0)
    response = httpx.get(
        f"{TELEGRAM_API_BASE}/bot{bot_token}/getUpdates",
        params={
            "offset": offset,
            "timeout": timeout,
            "allowed_updates": json.dumps(["message", "callback_query"]),
        },
        timeout=timeout + 10,
    )
    response.raise_for_status()
    updates = response.json().get("result", [])
    if updates:
        last = max(u.get("update_id", 0) for u in updates)
        _offset_path(output_folder).write_text(
            json.dumps({"offset": last + 1}), encoding="utf-8"
        )
    return updates


def poll_control_commands(
    bot_token: str, chat_id: str, output_folder: Path
) -> list[dict]:
    """Опрос + разбор команд за один вызов (см. poll_bot_updates)."""
    return parse_control_commands(
        poll_bot_updates(bot_token, output_folder), chat_id
    )


def parse_control_commands(updates: list[dict], chat_id: str) -> list[dict]:
    """Команды удалённого управления демоном из уже прочитанных
    обновлений: {"action": "status"|"help"|"pause"|"resume"|
    "send_draft"|"skip_draft", ...}."""
    commands = []
    for update in updates:
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
        match = _SEND_DRAFT_RE.match(text)
        if match:
            commands.append(
                {"action": "send_draft", "code": match.group(1).lower()}
            )
            continue
        match = _SKIP_DRAFT_RE.match(text)
        if match:
            commands.append(
                {"action": "skip_draft", "code": match.group(1).lower()}
            )
            continue
        match = _PAUSE_RE.match(text)
        if match:
            commands.append(
                {"action": "pause", "source": _SOURCE_ALIASES.get(match.group(1).lower(), match.group(1).lower())}
            )
            continue
        match = _RESUME_RE.match(text)
        if match:
            commands.append(
                {"action": "resume", "source": _SOURCE_ALIASES.get(match.group(1).lower(), match.group(1).lower())}
            )
            continue

    return commands
