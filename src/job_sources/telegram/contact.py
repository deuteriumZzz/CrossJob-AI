from __future__ import annotations

import re

# 5-32 символов — реальный диапазон длины username в Telegram.
_MENTION_RE = re.compile(r"@([a-zA-Z][a-zA-Z0-9_]{4,31})")


def extract_contact(text: str, channel: str) -> str | None:
    """Ищет @username в тексте поста — это и есть "куда писать" для
    большинства вакансий в Telegram (нет ни company/title, ни
    структурированной кнопки "откликнуться", как на площадках).
    Упоминание самого канала (репост из себя же) не считается
    контактом. Ровно одно кандидатное упоминание — берём его; ноль
    или несколько разных — не угадываем, оставляем вакансию только
    для ручного ответа (contact=None)."""
    mentions = {
        m for m in _MENTION_RE.findall(text) if m.lower() != channel.lower()
    }
    if len(mentions) == 1:
        return next(iter(mentions))
    return None
