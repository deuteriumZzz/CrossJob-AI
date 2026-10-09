"""«Пауза на всё» (Главная): отклики, рассылка и переписка от вашего имени
стоят разом, пока пауза не снята. Флаг — файл в папке результатов, а не
переменная процесса: его видят и окно, и бот в фоне (служба автозапуска),
и он переживает перезапуск. Входящие ответы HR и команды боту продолжают
читаться — пауза только про то, что уходит от вашего имени."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from src.utils.file_lock import state_file_lock

PAUSE_FILE = ".pause_all.json"

# Что работает и на паузе: только чтение входящих и команды боту.
ALWAYS_ON = frozenset(
    {
        "check_telegram_commands",
        "check_telegram_replies",
        "check_email_replies",
    }
)


def pause_state(output_folder: Path) -> dict:
    try:
        data = json.loads(
            (Path(output_folder) / PAUSE_FILE).read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    return {
        "paused": bool(data.get("paused")),
        "since": str(data.get("since") or ""),
    }


def is_paused(output_folder: Path | None) -> bool:
    return output_folder is not None and pause_state(output_folder)["paused"]


def set_paused(output_folder: Path, paused: bool) -> dict:
    path = Path(output_folder) / PAUSE_FILE
    state = {
        "paused": paused,
        "since": datetime.now().astimezone().isoformat() if paused else "",
    }
    with state_file_lock(path):
        path.write_text(json.dumps(state), encoding="utf-8")
    return state
