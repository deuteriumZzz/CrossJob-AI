from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

from src.utils.file_lock import state_file_lock

RunStatus = Literal["ok", "error", "blocked"]


def _state_path(output_folder: Path) -> Path:
    return output_folder / ".scheduler_state.json"


def load_state(output_folder: Path) -> dict:
    path = _state_path(output_folder)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        # ponytail: unlocked reads can race a concurrent write (write_text isn't atomic);
        # treat a torn read as "no state yet" rather than crashing the caller.
        return {}


def _save_state(output_folder: Path, state: dict) -> None:
    path = _state_path(output_folder)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def record_run_result(
    output_folder: Path,
    source: str,
    status: RunStatus,
    next_run: datetime,
    run_at: datetime,
    error: Optional[str] = None,
) -> None:
    """Фиксирует результат одного тика планировщика для источника —
    читает web UI (Фаза B), чтобы показать 🟢/🟡/🔴 и время следующего
    запуска без парсинга логов. Заблокировано на время
    read-modify-write — демон/ручной запуск/генерация резюме в
    дашборде работают в отдельных потоках и могут писать почти
    одновременно."""
    with state_file_lock(_state_path(output_folder)):
        state = load_state(output_folder)
        state[source] = {
            "last_run": run_at.isoformat(),
            "next_run": next_run.isoformat(),
            "status": status,
            "last_error": error,
        }
        _save_state(output_folder, state)


def get_next_run(output_folder: Path, source: str) -> Optional[datetime]:
    entry = load_state(output_folder).get(source)
    if not entry or not entry.get("next_run"):
        return None
    return datetime.fromisoformat(entry["next_run"])
