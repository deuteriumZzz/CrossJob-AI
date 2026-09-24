"""Резервная копия данных раз в день: база компаний, рассылки, отклики,
переписка, черновики — в data_folder/backups/ГГГГ-ММ-ДД/, хранятся 7 дней.
Если файл испортится или что-то удалили по ошибке — есть откуда вернуть."""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

from src.logging import logger

BACKUP_FILES = (
    "contact_book.json", "campaigns.json", "applied_log.json",
    "telegram_conversations.json", ".hr_reply_drafts.json",
)
KEEP_DAYS = 7


def daily_backup(output_folder: Path, today: date | None = None) -> Path | None:
    """Копия за сегодня, если её ещё нет. Возвращает папку копии или None."""
    root = output_folder.parent / "backups"
    target = root / (today or date.today()).isoformat()
    if target.exists():
        return None
    files = [output_folder / name for name in BACKUP_FILES if (output_folder / name).exists()]
    if not files:
        return None
    try:
        target.mkdir(parents=True)
        for f in files:
            shutil.copy2(f, target / f.name)
        # Старше недели — удаляем, папки названы датой, сортируются сами.
        for old in sorted(p for p in root.iterdir() if p.is_dir())[:-KEEP_DAYS]:
            shutil.rmtree(old, ignore_errors=True)
    except OSError as e:
        logger.warning(f"Резервная копия не сделана: {e}")
        return None
    return target
