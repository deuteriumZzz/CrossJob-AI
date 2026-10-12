from __future__ import annotations

import re

from src.job_sources.contact_book import contacts_from_text

# 5-32 символов — реальный диапазон длины username в Telegram.
_MENTION_RE = re.compile(r"@([a-zA-Z][a-zA-Z0-9_]{4,31})")
_RECIPIENT_CUE_RE = re.compile(
    r"\b(?:контакты?|связь|пишите|напишите|написать|"
    r"отклик(?:нуться|айтесь|нуться можно)?|"
    r"отправ(?:ьте|лять)|contact|apply|send|dm)\b",
    re.IGNORECASE,
)
_SOURCE_LINE_RE = re.compile(
    r"^\s*(?:канал|источник|публикация|"
    r"(?:вакансия|пост)\s+опубликован[ао]?\s+в)\b",
    re.IGNORECASE,
)


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


def post_recipient_options(text: str, channel: str) -> list[dict]:
    """Адресаты, которых пост предлагает для отклика.

    Явные строки «Связь/Контакты/пишите» имеют приоритет над прочими
    упоминаниями. Если такой строки нет, единственный найденный адрес
    можно предложить с пометкой single; несколько адресов без указания
    роли остаются неоднозначными и не выбираются автоматически.
    """
    source_handles = {
        (contact["kind"], contact["value"].lower())
        for line in text.splitlines()
        if _SOURCE_LINE_RE.search(line)
        for contact in contacts_from_text(line, exclude=(channel,))
        if contact["kind"] == "telegram"
    }
    all_contacts = [
        contact
        for contact in contacts_from_text(text, exclude=(channel,))
        if contact["kind"] in {"telegram", "email"}
        and (contact["kind"], contact["value"].lower()) not in source_handles
    ]
    explicit = {
        (contact["kind"], contact["value"].lower())
        for line in text.splitlines()
        if _RECIPIENT_CUE_RE.search(line)
        for contact in contacts_from_text(line, exclude=(channel,))
        if contact["kind"] in {"telegram", "email"}
    }
    if explicit:
        return [
            {**contact, "source": "explicit"}
            for contact in all_contacts
            if (contact["kind"], contact["value"].lower()) in explicit
        ]
    if len(all_contacts) == 1:
        return [{**all_contacts[0], "source": "single"}]
    return []


def normalize_post_contacts(post: dict) -> dict:
    """Восстанавливает адреса в старом посте без записи в историю.

    Сохранённый список сохраняем: раньше под ним могли быть черновики
    и отправки. Из текста добавляем только отсутствующие адреса.
    """
    text = str(post.get("text") or "")
    channel = str(post.get("channel") or "")
    hirify = post.get("source") == "hirify"
    stored = [
        item
        for item in post.get("contacts") or []
        if isinstance(item, dict)
        and item.get("kind") in {"telegram", "email", "linkedin"}
        and isinstance(item.get("value"), str)
        and item["value"]
    ]
    known = {(item["kind"], item["value"].lower()) for item in stored}
    recovered = (
        []
        if hirify
        else [
            item
            for item in contacts_from_text(text, exclude=(channel,))
            if (item["kind"], item["value"].lower()) not in known
        ]
    )
    options = [] if hirify else post_recipient_options(text, channel)
    option_keys = {(c["kind"], c["value"].lower()) for c in options}
    stored_options = [
        {
            "kind": item["kind"],
            "value": item["value"],
            "source": (
                "manual" if item.get("source") == "manual" else "hirify"
            ),
        }
        for item in stored
        if (
            item.get("source") == "manual"
            or (hirify and str(item.get("source", "")).startswith("Hirify:"))
        )
        and item["kind"] in {"telegram", "email"}
        and (item["kind"], item["value"].lower()) not in option_keys
    ]
    return {
        **post,
        "contacts": stored + recovered,
        "recipient_options": options + stored_options,
    }
