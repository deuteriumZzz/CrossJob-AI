"""hirify.me: список вакансий и страница вакансии (открытый HTML).

Список — `/?search=<запрос>&page=<n>` (15 на странице), ссылки вида
`/jobs/<id>-<slug>`. На странице вакансии — разметка schema.org
JobPosting (название, компания, текст, дата, формат, тип занятости).
Контакты HR и название Telegram-канала спрятаны за бесплатным аккаунтом
(проверено 2026-10-08) — их берёт client.show_contacts из вашего входа."""

from __future__ import annotations

import json
import re
from typing import Optional

from src.job import Job
from src.job_sources.html_text import strip_html

BASE_URL = "https://hirify.me"
_JOB_LINK = re.compile(r'href="/jobs/(\d+)-([^"?#]*)[^"]*"')
_LD_JSON = re.compile(
    r'<script type="application/ld\+json">(.*?)</script>', re.S
)
_CHANNEL = re.compile(
    r"Вакансия из Telegram канала\s*[-–—:]?\s*(?:https?://t\.me/|@)?"
    r"([A-Za-z][A-Za-z0-9_]{4,31})"
)


def parse_list(html: str) -> list[dict]:
    """[{id, slug}] в порядке выдачи, без повторов."""
    seen: set[str] = set()
    found = []
    for job_id, slug in _JOB_LINK.findall(html):
        if job_id not in seen:
            seen.add(job_id)
            found.append({"id": job_id, "slug": slug})
    return found


def _posting(html: str) -> Optional[dict]:
    for block in _LD_JSON.findall(html):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        for item in data if isinstance(data, list) else [data]:
            if isinstance(item, dict) and item.get("@type") == "JobPosting":
                return item
    return None


def parse_job(html: str, job_id: str) -> Optional[tuple[Job, dict]]:
    """(Job, meta) со страницы вакансии; None — разметки вакансии нет.
    meta: posted_at (ISO), employment (FULL_TIME…), remote (bool)."""
    item = _posting(html)
    if item is None:
        return None
    org = item.get("hiringOrganization") or {}
    company = org.get("name", "") if isinstance(org, dict) else str(org)
    remote = item.get("jobLocationType") == "TELECOMMUTE"
    countries = []
    for place in item.get("applicantLocationRequirements") or []:
        if isinstance(place, dict) and place.get("name"):
            countries.append(str(place["name"]))
    employment = item.get("employmentType") or []
    if isinstance(employment, str):
        employment = [employment]
    job = Job(
        role=str(item.get("title", "")).strip(),
        company=str(company).strip(),
        location=", ".join(
            filter(None, ["Remote" if remote else "", *countries])
        ),
        link=item.get("url") or f"{BASE_URL}/jobs/{job_id}",
        description=strip_html(str(item.get("description", ""))),
        source="hirify",
        external_id=job_id,
    )
    meta = {
        "posted_at": item.get("datePosted", ""),
        "employment": [str(e) for e in employment],
        "remote": remote,
    }
    return job, meta


def channel_from_text(text: str) -> str:
    """Telegram-канал, из которого взята вакансия (виден после входа)."""
    match = _CHANNEL.search(text or "")
    return match.group(1) if match else ""


_CONTACTS_BLOCK = re.compile(
    r"Контакты:?(.*?)(?:Будьте осторожны|Текст вакансии|Пожаловаться|$)",
    re.S,
)


def contacts_block(page_text: str) -> str:
    """Текст блока «Контакты» (без подвала и ссылок самого сайта)."""
    blocks = _CONTACTS_BLOCK.findall(page_text or "")
    return " ".join(b.strip() for b in blocks if b.strip())
