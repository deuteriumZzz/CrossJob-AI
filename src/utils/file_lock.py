from __future__ import annotations

from pathlib import Path

from filelock import FileLock


def state_file_lock(path: Path, timeout: float = 10) -> FileLock:
    """Общий .lock рядом с JSON-файлом состояния — защищает
    read-modify-write от гонки между потоками дашборда (демон,
    ручной запуск, генерация резюме), которые могут писать в один и
    тот же файл (applied_log.json/scheduler_state.json/
    .blocked_until.json/.llm_usage.json) почти одновременно."""
    return FileLock(str(path) + ".lock", timeout=timeout)
