"""Единый словарь интерфейса, «Нужно ваше решение» и сообщений бота
(docs/PLAN.md, раздел F, добавка 4): одни названия площадок и четыре
статуса — работает, пауза, нужен вход, ошибка. Те же слова, что в
app.js (SOURCE_LABELS, sourceRowModel)."""

from __future__ import annotations

PLATFORM_NAMES = {
    "headhunter": "HeadHunter",
    "geekjob": "geekjob.ru",
    "telegram": "Telegram",
    "getmatch": "GetMatch",
    "linkedin": "LinkedIn",
    "habr_career": "Habr Career",
    "wellfound": "Wellfound",
    "himalayas": "Himalayas",
    "djinni": "Djinni",
    "avito": "Авито Работа",
    "direct": "Сайты компаний",
    "talanto": "Talanto",
    "hirify": "Hirify",
}

STATUS_WORDS = {
    "ok": "работает",
    "paused": "пауза",
    "login": "нужен вход",
    "error": "ошибка",
}

# Площадка ждала ручного входа и не дождалась (auth.py у площадок:
# «Timed out waiting for … login.»).
LOGIN_MARKERS = ("timed out waiting for", "требует ручного входа")


def platform_name(name: str) -> str:
    return PLATFORM_NAMES.get(name, name)


def error_kind(raw: str | None) -> str:
    """ "login" — нужен вход, иначе "error"."""
    lowered = (raw or "").lower()
    if any(m in lowered for m in LOGIN_MARKERS) and "login" in lowered:
        return "login"
    return "error"


def platform_state(
    status: str | None, paused: bool, raw_error: str | None
) -> str:
    """Ключ STATUS_WORDS по состоянию площадки из scheduler_state."""
    if paused:
        return "paused"
    if status == "error":
        return error_kind(raw_error)
    return "ok"
