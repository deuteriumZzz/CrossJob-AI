"""Контакты только из источника — текст вакансии или проверенный Hunter.
Угаданные адреса (имя.фамилия@домен) и адреса от LLM не используются:
именно такие оказывались неактуальными."""

from __future__ import annotations

import re

import httpx

_OBFUSCATED_RE = [
    (re.compile(r"\s*[\[(]\s*at\s*[\])]\s*", re.IGNORECASE), "@"),
    (re.compile(r"\s*[\[(]\s*dot\s*[\])]\s*", re.IGNORECASE), "."),
    (re.compile(r"\s+at\s+(?=[\w-]+\s*(?:\.|\[dot\]|\(dot\)))", re.IGNORECASE), "@"),
]
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Служебные ящики, куда писать бесполезно (идея отсева — JobHunter).
_SKIP_PREFIXES = (
    "noreply", "no-reply", "donotreply", "privacy", "legal", "security",
    "abuse", "support", "billing", "press", "gdpr", "dpo",
)
_SKIP_DOMAINS = ("example.com", "sentry.io", "domain.com", "email.com")


def extract_emails(text: str) -> list[str]:
    """Адреса из текста вакансии, включая запись "name [at] co [dot] com"."""
    clean = text
    for pattern, repl in _OBFUSCATED_RE:
        clean = pattern.sub(repl, clean)
    found: list[str] = []
    for raw in _EMAIL_RE.findall(clean):
        email = raw.strip(".").lower()
        local, _, domain = email.partition("@")
        if local.startswith(_SKIP_PREFIXES) or domain in _SKIP_DOMAINS:
            continue
        if email not in found:
            found.append(email)
    return found


HUNTER_API = "https://api.hunter.io/v2"


def hunter_hr_contacts(domain: str, api_key: str) -> list[dict]:
    """Проверенные адреса отдела кадров компании через Hunter. Сначала
    бесплатный email-count — платный domain-search только если у
    Hunter вообще есть адреса этого домена (идея из reporadar).
    Возвращает [{email, name, position, confidence}] с confidence>=80."""
    count = httpx.get(
        f"{HUNTER_API}/email-count",
        params={"domain": domain, "api_key": api_key},
        timeout=15,
    )
    count.raise_for_status()
    if not count.json()["data"]["total"]:
        return []
    search = httpx.get(
        f"{HUNTER_API}/domain-search",
        params={"domain": domain, "department": "hr", "api_key": api_key},
        timeout=15,
    )
    search.raise_for_status()
    return [
        {
            "email": e["value"],
            "name": " ".join(
                filter(None, [e.get("first_name"), e.get("last_name")])
            ),
            "position": e.get("position") or "",
            "confidence": e.get("confidence") or 0,
        }
        for e in search.json()["data"].get("emails", [])
        if (e.get("confidence") or 0) >= 80
    ]
