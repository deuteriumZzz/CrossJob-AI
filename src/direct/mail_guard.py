"""Защита Gmail при рассылке: письма уходят как у человека, а не пачкой.

- Дневной лимит — ваш (Настройки → Почта и письма), но с «разогревом»:
  новый для рассылок ящик начинает с 15 писем в день и прибавляет по 5
  за каждый день, когда письма уже уходили, — пока не дойдёт до вашего
  лимита. Резкий рост с нуля до сотен писем — главный признак спама.
- Только в рабочее время (по умолчанию будни 9–19) — письма в 3 ночи
  выдают бота.
- Паузы случайные и растянуты на весь рабочий день, иногда — перерыв
  подольше («отошёл за кофе»).
- Много возвратов за сутки (адреса не существуют) — стоп до завтра:
  Gmail режет отправителей с высоким процентом возвратов."""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

WARMUP_START, WARMUP_STEP = 15, 5
BOUNCE_STOP = 3  # по умолчанию: столько возвратов за сутки — и отправка встаёт до завтра
BOUNCE_STOP_MAX = 30
MIN_PAUSE, MAX_PAUSE = 120, 40 * 60


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _events(output_folder: Path) -> tuple[list[datetime], list[datetime]]:
    """Когда уходили письма HR и когда приходили возвраты — из рассылок,
    писем к откликам и писем, отмеченных на контактах Базы."""
    sent: list[str] = []
    bounced: list[str] = []
    for campaign in _load(output_folder / "campaigns.json").values():
        for item in campaign.get("items", {}).values():
            sent.append(item.get("sent_at") or "")
            bounced.append(item.get("bounced_at") or "")
    for entry in _load(output_folder / "applied_log.json").get("applications", []):
        sent.append(entry.get("outreach_sent_at") or "")
    for card in _load(output_folder / "contact_book.json").get("companies", {}).values():
        for contact in card.get("contacts", []):
            sent.append(contact.get("sent_at") or "")
            bounced.append(contact.get("bounced_at") or "")
    parse = lambda xs: [datetime.fromisoformat(x) for x in xs if x]  # noqa: E731
    return parse(sent), parse(bounced)


def settings(parameters: dict) -> dict:
    direct = parameters.get("direct") or {}
    return {
        "daily_limit": int(direct.get("email_daily_limit", 30)),
        "warmup": direct.get("warmup", True) is not False,
        "send_from": int(direct.get("send_from", 9)),
        "send_to": int(direct.get("send_to", 19)),
        "weekdays_only": direct.get("weekdays_only", True) is not False,
        # Возвратов за сутки до стопа — настраивается (Защита почты), но не
        # выключается: волна возвратов уводит в спам письма и живым HR.
        "bounce_stop": min(BOUNCE_STOP_MAX, max(1, int(direct.get("bounce_stop", BOUNCE_STOP)))),
    }


def _in_window(moment: datetime, s: dict) -> bool:
    if s["weekdays_only"] and moment.weekday() >= 5:
        return False
    return s["send_from"] <= moment.hour < s["send_to"]


def next_window(moment: datetime, s: dict) -> datetime:
    """Ближайшее начало времени отправки (или сейчас, если оно идёт)."""
    if _in_window(moment, s):
        return moment
    day = moment.replace(hour=s["send_from"], minute=0, second=0, microsecond=0)
    if moment.hour >= s["send_from"]:
        day += timedelta(days=1)
    while s["weekdays_only"] and day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def plan(parameters: dict, output_folder: Path, now: datetime | None = None) -> dict:
    """Сколько писем можно сегодня и можно ли прямо сейчас."""
    now = now or datetime.now().astimezone()
    s = settings(parameters)
    sent, bounced = _events(output_folder)
    today = now.date()
    days_active = len({d.date() for d in sent if d.date() < today})
    limit = s["daily_limit"]
    if s["warmup"]:
        limit = min(limit, WARMUP_START + WARMUP_STEP * days_active)
    sent_today = sum(1 for d in sent if d.date() == today)
    recent_bounces = sum(1 for d in bounced if now - d < timedelta(hours=24))
    in_window = _in_window(now, s)
    reason = ""
    if recent_bounces >= s["bounce_stop"]:
        reason = f"Возвратов за сутки: {recent_bounces} — пауза до завтра, чтобы Gmail не счёл это спамом"
    elif sent_today >= limit:
        reason = f"Дневной лимит писем ({limit}) исчерпан — продолжу завтра"
    elif not in_window:
        reason = f"Вне времени отправки — продолжу {next_window(now, s).strftime('%d.%m в %H:%M')}"
    return {
        **s,
        "limit": limit,
        "warmup_day": days_active + 1,
        "sent_today": sent_today,
        "left_today": max(0, limit - sent_today),
        "in_window": in_window,
        "recent_bounces": recent_bounces,
        "bounce_stopped": recent_bounces >= s["bounce_stop"],
        "can_send": not reason,
        "reason": reason,
    }


def human_pause(p: dict, now: datetime | None = None) -> float:
    """Пауза до следующего письма: оставшиеся письма дня равномерно по
    оставшемуся рабочему времени, ±50% случайно, иногда перерыв."""
    now = now or datetime.now().astimezone()
    end = now.replace(hour=p["send_to"], minute=0, second=0, microsecond=0)
    left = max(1, p["left_today"])
    pace = max(0.0, (end - now).total_seconds()) / left
    pause = random.uniform(0.5, 1.5) * pace
    if random.random() < 1 / 6:
        pause += random.uniform(10 * 60, 25 * 60)
    return min(MAX_PAUSE, max(MIN_PAUSE, pause))


def days_needed(p: dict, letters: int) -> int:
    """Сколько дней отправки уйдёт на letters писем — с учётом разогрева."""
    days, limit, left = 0, p["limit"], letters
    while left > 0 and days < 3650:
        left -= limit
        days += 1
        if p["warmup"]:
            limit = min(p["daily_limit"], limit + WARMUP_STEP)
    return days
