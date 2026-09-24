"""Поиск вакансий на djinni.co — обычными HTTP-запросами, без браузера.

Каждая страница выдачи /jobs/ содержит JSON-LD со списком JobPosting
(название, компания, полное описание, ссылка, дата, удалёнка) —
подтверждено вживую 2026-09-25. Это надёжнее селекторов карточек:
структурированные данные для поисковиков меняют редко. robots.txt
раздел /jobs/ не запрещает.

Фильтр по технологии — категория primary_keyword (Python и т.п.),
остальные латинские слова должности идут в полнотекстовый all_keywords."""

from __future__ import annotations

import json
import random
import re
import time
from html import unescape
from typing import Optional

import httpx

from src.job import Job
from src.job_sources.blacklist_filter import passes_blacklists
from src.job_sources.block_detection import raise_if_blocked
from src.job_sources.preferences import effective_list

BASE = "https://djinni.co"
PAGES_PER_POSITION = 3  # по 15 вакансий на странице
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126 Safari/537.36"
)
_LD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)

# Слово в должности → категория Djinni. ponytail: подтверждена вживую
# только «Python»; остальные — по названиям категорий сайта. Неизвестная
# технология просто уходит в полнотекстовый поиск.
_CATEGORIES = {
    "python": "Python", "django": "Python", "fastapi": "Python",
    "javascript": "JavaScript", "typescript": "JavaScript",
    "java": "Java", "golang": "Golang", "go": "Golang", "php": "PHP",
    "ruby": "Ruby", "node": "Node.js", "nodejs": "Node.js", ".net": ".NET",
    "c#": ".NET", "scala": "Scala", "rust": "Rust", "devops": "DevOps",
    "qa": "QA", "flutter": "Flutter", "ios": "iOS", "android": "Android",
}


def search_params(position: str, page: int = 1) -> dict:
    """«Python Backend Developer» → категория Python. Без узнаваемой
    технологии — полнотекстовый поиск по латинским словам должности
    (русские «разработчик» на Djinni почти не встречаются)."""
    words = position.split()
    category = next((_CATEGORIES[w.lower()] for w in words if w.lower() in _CATEGORIES), "")
    params: dict = {}
    if category:
        params["primary_keyword"] = category
    else:
        latin = " ".join(w for w in words if re.fullmatch(r"[A-Za-z0-9+#.-]+", w))
        if latin:
            params.update(all_keywords=latin, search_type="full-text")
    if page > 1:
        params["page"] = page
    return params


def parse_jobs(html: str) -> list[Job]:
    """JobPosting из JSON-LD страницы выдачи → Job."""
    jobs: list[Job] = []
    for block in _LD_RE.findall(html):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        for item in data if isinstance(data, list) else [data]:
            if not isinstance(item, dict) or item.get("@type") != "JobPosting" or not item.get("url"):
                continue
            countries = [
                ((r.get("address") or {}).get("addressCountry") or "")
                for r in item.get("applicantLocationRequirements") or []
                if isinstance(r, dict)
            ]
            remote = item.get("jobLocationType") == "TELECOMMUTE"
            org = item.get("hiringOrganization") or ""
            # Компания бывает объектом Organization, а бывает просто строкой.
            company = org.get("name", "") if isinstance(org, dict) else str(org)
            jobs.append(Job(
                role=unescape(item.get("title", "")),
                company=unescape(company),
                location=", ".join(filter(None, ["Remote" if remote else "", *countries])),
                link=item["url"],
                apply_method="djinni",
                description=unescape(item.get("description", "")),
                source="djinni",
                external_id=str(item.get("identifier") or item["url"]),
            ))
    return jobs


def search(preferences: dict, client: Optional[httpx.Client] = None) -> list[Job]:
    """Все должности из «Что ищу» (или свои у Djinni), по
    PAGES_PER_POSITION страниц, без повторов и с чёрными списками."""
    own = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=20, follow_redirects=True)
    seen: set[str] = set()
    jobs: list[Job] = []
    try:
        for position in effective_list(preferences, "djinni", "positions"):
            for page in range(1, PAGES_PER_POSITION + 1):
                response = client.get(f"{BASE}/jobs/", params=search_params(position, page))
                found = parse_jobs(response.text)
                # В обычной странице Djinni есть скрипт reCAPTCHA формы входа —
                # слово «captcha» само по себе не блокировка. Блок — это 403/429
                # или страница без единой вакансии.
                if response.status_code in (403, 429) or (not found and page == 1):
                    raise_if_blocked(response)
                for job in found:
                    if job.external_id not in seen and passes_blacklists(job, preferences):
                        seen.add(job.external_id)
                        jobs.append(job)
                if len(found) < 15:
                    break  # последняя страница
                time.sleep(random.uniform(1.0, 2.5))  # вежливо к сайту
    finally:
        if own:
            client.close()
    return jobs
