from __future__ import annotations

import os
from pathlib import Path

from filelock import FileLock


def state_file_lock(path: Path, timeout: float = 10) -> FileLock:
    """Общий .lock рядом с JSON-файлом состояния — защищает
    read-modify-write от гонки между потоками дашборда (демон,
    ручной запуск, генерация резюме), которые могут писать в один и
    тот же файл (applied_log.json/scheduler_state.json/
    .blocked_until.json/.llm_usage.json) почти одновременно."""
    return FileLock(str(path) + ".lock", timeout=timeout)


def atomic_write_text(path: Path, text: str) -> None:
    """Запись целиком через временный файл + os.replace: читатели без
    блокировки (дашборд) видят либо старое, либо новое содержимое, а не
    пустой файл посреди write_text — живой случай: JSONDecodeError
    «Expecting value: line 1 column 1» в /api/status и /api/stats."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
