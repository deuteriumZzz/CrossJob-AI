"""Резервная копия данных раз в день: база компаний, рассылки, отклики,
переписка, черновики — в data_folder/backups/ГГГГ-ММ-ДД/, хранятся 7 дней.
Если файл испортится или что-то удалили по ошибке — есть откуда вернуть."""

from __future__ import annotations

import re
import shutil
from datetime import date, datetime
from pathlib import Path

from src.logging import logger

BACKUP_FILES = (
    "contact_book.json",
    "campaigns.json",
    "applied_log.json",
    "telegram_conversations.json",
    ".hr_reply_drafts.json",
)
KEEP_DAYS = 7
# Копии «Сделать копию сейчас» (Настройки → Резервные копии) — в папках
# ГГГГ-ММ-ДД-ЧЧММСС рядом с дневными, считаются отдельно: ручная копия не
# вытесняет дневные, и наоборот.
KEEP_MANUAL = 5
_DAILY_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MANUAL_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}-\d{6}$")


def is_backup_name(name: str) -> bool:
    return bool(_DAILY_NAME.match(name) or _MANUAL_NAME.match(name))


def daily_backup(
    output_folder: Path, today: date | None = None
) -> Path | None:
    """Копия за сегодня, если её ещё нет. Возвращает папку копии или None."""
    root = output_folder.parent / "backups"
    target = root / (today or date.today()).isoformat()
    if target.exists():
        return None
    files = [
        output_folder / name
        for name in BACKUP_FILES
        if (output_folder / name).exists()
    ]
    if not files:
        return None
    try:
        target.mkdir(parents=True)
    except FileExistsError:
        # daily_backup() вызывается и из планировщика (scheduler.py), и
        # при первом запросе к вебui (api.py get_ctx()) — на старте
        # приложения оба могут пройти проверку "target.exists()" выше
        # почти одновременно и оба попытаться создать папку. Кто-то
        # один уже сделал копию (то, ради чего эта функция) — это не
        # ошибка, предупреждение из-за неё только пугало пользователя
        # (подтверждено на реальном логе: "File exists" дважды подряд
        # при старте, хотя копия была сделана успешно).
        return None
    try:
        for f in files:
            shutil.copy2(f, target / f.name)
        # Старше недели — удаляем, папки названы датой, сортируются сами.
        for old in sorted(
            p
            for p in root.iterdir()
            if p.is_dir() and not _MANUAL_NAME.match(p.name)
        )[:-KEEP_DAYS]:
            shutil.rmtree(old, ignore_errors=True)
    except OSError as e:
        logger.warning(f"Резервная копия не сделана: {e}")
        return None
    return target


def backup_now(output_folder: Path, now: datetime | None = None) -> Path:
    """Копия прямо сейчас, сколько бы их ни было за день. Бросает OSError,
    если копию сделать не удалось, и FileNotFoundError, если копировать
    нечего — кнопка в настройках должна честно сказать, что вышло."""
    root = output_folder.parent / "backups"
    files = [
        output_folder / name
        for name in BACKUP_FILES
        if (output_folder / name).exists()
    ]
    if not files:
        raise FileNotFoundError("Пока нечего копировать — данных ещё нет")
    target = root / (now or datetime.now()).strftime("%Y-%m-%d-%H%M%S")
    target.mkdir(parents=True, exist_ok=True)
    for f in files:
        shutil.copy2(f, target / f.name)
    for old in sorted(
        p for p in root.iterdir() if p.is_dir() and _MANUAL_NAME.match(p.name)
    )[:-KEEP_MANUAL]:
        shutil.rmtree(old, ignore_errors=True)
    return target
