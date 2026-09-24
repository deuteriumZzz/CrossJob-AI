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


def _countries(item: dict) -> list[str]:
    """Страны, откуда компания рассматривает кандидатов (ISO3). Djinni
    пишет их то списком, то одним объектом, то строкой."""
    raw = item.get("applicantLocationRequirements") or []
    result = []
    for r in raw if isinstance(raw, list) else [raw]:
        address = r.get("address", "") if isinstance(r, dict) else r
        code = address.get("addressCountry", "") if isinstance(address, dict) else address
        if isinstance(code, str) and code:
            result.append(code)
    return result


def parse_jobs(html: str, country: str = "", max_months: Optional[float] = None) -> list[Job]:
    """JobPosting из JSON-LD страницы выдачи → Job. country/max_months —
    сразу отсеять то, куда Djinni всё равно не даст откликнуться: вакансия
    не для вашей страны или требует стажа больше max_months."""
    jobs: list[Job] = []
    for block in _LD_RE.findall(html):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        for item in data if isinstance(data, list) else [data]:
            if not isinstance(item, dict) or item.get("@type") != "JobPosting" or not item.get("url"):
                continue
            countries = _countries(item)
            experience = item.get("experienceRequirements")
            months = experience.get("monthsOfExperience") if isinstance(experience, dict) else None
            if country and countries and country.upper() not in countries:
                continue
            if max_months is not None and months and months > max_months:
                continue
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
    own_settings = preferences.get("djinni") or {}
    country = str(own_settings.get("country") or "")
    years = own_settings.get("experience_years")
    # Стаж с запасом в год: «от 2 лет» при ваших 1.5 Djinni ещё пропускает не всегда,
    # но «от 5 лет» — точно нет, такие даже не оцениваем.
    max_months = float(years) * 12 + 12 if years is not None else None
    try:
        for position in effective_list(preferences, "djinni", "positions"):
            for page in range(1, PAGES_PER_POSITION + 1):
                response = client.get(f"{BASE}/jobs/", params=search_params(position, page))
                page_jobs = parse_jobs(response.text)
                found = parse_jobs(response.text, country, max_months)
                # В обычной странице Djinni есть скрипт reCAPTCHA формы входа —
                # слово «captcha» само по себе не блокировка. Блок — это 403/429
                # или страница без единой вакансии.
                if response.status_code in (403, 429) or (not page_jobs and page == 1):
                    raise_if_blocked(response)
                for job in found:
                    if job.external_id not in seen and passes_blacklists(job, preferences):
                        seen.add(job.external_id)
                        jobs.append(job)
                if len(page_jobs) < 15:
                    break  # последняя страница
                time.sleep(random.uniform(1.0, 2.5))  # вежливо к сайту
    finally:
        if own:
            client.close()
    return jobs
