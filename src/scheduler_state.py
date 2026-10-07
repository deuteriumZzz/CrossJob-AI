from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

from src.utils.file_lock import atomic_write_text, state_file_lock

RunStatus = Literal["ok", "error", "blocked"]
RUN_HISTORY_FILE = ".run_history.jsonl"


def _state_path(output_folder: Path) -> Path:
    return output_folder / ".scheduler_state.json"


def load_state(output_folder: Path) -> dict:
    path = _state_path(output_folder)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        # ponytail: unlocked reads can race a concurrent write
        # (write_text isn't atomic); treat a torn read as "no state
        # yet" rather than crashing the caller.
        return {}


def _save_state(output_folder: Path, state: dict) -> None:
    # Атомарно: «порванное» чтение раньше давало {} — и планировщик
    # считал, что пора запускать все площадки разом.
    atomic_write_text(_state_path(output_folder), json.dumps(state, indent=2))


def record_run_result(
    output_folder: Path,
    source: str,
    status: RunStatus,
    next_run: datetime,
    run_at: datetime,
    error: Optional[str] = None,
    idle_streak: Optional[int] = None,
) -> None:
    """Фиксирует результат одного тика планировщика для источника —
    читает web UI (Фаза B), чтобы показать 🟢/🟡/🔴 и время следующего
    запуска без парсинга логов. Заблокировано на время
    read-modify-write — демон/ручной запуск/генерация резюме в
    дашборде работают в отдельных потоках и могут писать почти
    одновременно."""
    # Сколько длился ход — без этого не понять, какая площадка съедает
    # время круга; пишется и в историю (в состоянии хранится только
    # последний запуск).
    duration = round(
        max(0.0, (datetime.now(run_at.tzinfo) - run_at).total_seconds()), 1
    )
    with state_file_lock(_state_path(output_folder)):
        state = load_state(output_folder)
        state[source] = {
            "last_run": run_at.isoformat(),
            "next_run": next_run.isoformat(),
            "status": status,
            "last_error": error,
            "duration_seconds": duration,
        }
        if idle_streak is not None:
            state[source]["idle_streak"] = idle_streak
        _save_state(output_folder, state)
        try:
            with (output_folder / RUN_HISTORY_FILE).open(
                "a", encoding="utf-8"
            ) as fh:
                fh.write(
                    json.dumps(
                        {
                            "source": source,
                            "status": status,
                            "run_at": run_at.isoformat(),
                            "duration_seconds": duration,
                            "error": error,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        except OSError:
            pass


def get_next_run(output_folder: Path, source: str) -> Optional[datetime]:
    entry = load_state(output_folder).get(source)
    if not entry or not entry.get("next_run"):
        return None
    return datetime.fromisoformat(entry["next_run"])


def get_idle_streak(output_folder: Path, source: str) -> int:
    """Сколько ходов подряд площадка не нашла ничего нового."""
    return int(
        (load_state(output_folder).get(source) or {}).get("idle_streak", 0)
    )
