"""Вакансии прямо с сайтов компаний: у большинства раздел «Карьера»
работает на одной из систем найма с открытым JSON API (без входа).
Идея автоопределения ATS по сайту — из mattyray/reporadar (код не
заимствован: у репозитория нет лицензии), адреса API — публичные."""

from __future__ import annotations

import re
from html import unescape

import httpx

from src.job import Job

TIMEOUT = 15
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; CrossJob-AI)"}

API_URLS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true",
    "lever": "https://api.lever.co/v0/postings/{slug}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{slug}",
    "workable": "https://apply.workable.com/api/v1/widget/accounts/{slug}",
}

ATS_URL_PATTERNS = {
    "greenhouse": re.compile(
        r"(?:job-)?boards(?:-api)?\.greenhouse\.io/"
        r"(?:embed/job_board(?:/js)?\?for=|v1/boards/)?([\w-]+)"
    ),
    "lever": re.compile(r"jobs\.lever\.co/([\w-]+)"),
    "ashby": re.compile(r"jobs\.ashbyhq\.com/([\w.-]+)"),
    "workable": re.compile(r"apply\.workable\.com/([\w-]+)"),
}
_CAREERS_LINK_RE = re.compile(
    r'href=["\']([^"\']*(?:career|jobs?|join|hiring|vacanc|openings)[^"\']*)["\']',
    re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(html: str) -> str:
    return re.sub(r"\s+", " ", unescape(_TAG_RE.sub(" ", unescape(html)))).strip()


def _get(url: str) -> httpx.Response:
    return httpx.get(
        url, timeout=TIMEOUT, headers=_HEADERS, follow_redirects=True
    )


def find_ats_in_html(html: str) -> tuple[str, str] | None:
    for ats, pattern in ATS_URL_PATTERNS.items():
        match = pattern.search(html)
        if match:
            return ats, match.group(1)
    return None


def discover_ats(website: str) -> tuple[str, str] | None:
    """(ats, slug) по сайту компании: главная + до 5 ссылок вида
    careers/jobs, ищем в HTML адрес известной ATS. None — не нашли
    (самописная страница вакансий — только ручной отклик)."""
    if not website.startswith(("http://", "https://")):
        website = f"https://{website}"
    try:
        home = _get(website)
    except httpx.HTTPError:
        return None
    found = find_ats_in_html(home.text)
    if found:
        return found
    for link in _CAREERS_LINK_RE.findall(home.text)[:5]:
        url = str(home.url.join(link))
        try:
            found = find_ats_in_html(_get(url).text)
        except httpx.HTTPError:
            continue
        if found:
            return found
    # "about.gitlab.com" → "gitlab": имя домена перед зоной.
    labels = home.url.host.split(".")
    return probe_slug(labels[-2] if len(labels) >= 2 else labels[0])


def probe_slug(slug: str) -> tuple[str, str] | None:
    """Запасной путь, когда вакансии на сайте подгружаются скриптом и
    ссылки на ATS в HTML нет: пробуем имя домена как slug в каждой ATS,
    берём первую доску с вакансиями (идея probe из reporadar)."""
    for ats in API_URLS:
        try:
            if fetch_jobs({"ats": ats, "slug": slug, "name": slug}):
                return ats, slug
        except (httpx.HTTPError, ValueError, KeyError):
            continue
    return None


def fetch_jobs(company: dict) -> list[Job]:
    """company = {name, ats, slug}. Пустой список, если у компании на
    этой ATS нет доски (404) — не ошибка."""
    ats, slug, name = company["ats"], company["slug"], company["name"]
    response = _get(API_URLS[ats].format(slug=slug))
    if response.status_code == 404:
        return []
    response.raise_for_status()
    data = response.json()

    def job(**kw) -> Job:
        return Job(company=name, source="direct", company_url=company.get("website", ""), **kw)

    if ats == "greenhouse":
        return [
            job(
                role=j["title"],
                location=(j.get("location") or {}).get("name", ""),
                link=j["absolute_url"],
                description=_strip_html(j.get("content", "")),
                external_id=f"gh-{slug}-{j['id']}",
            )
            for j in data.get("jobs", [])
        ]
    if ats == "lever":
        return [
            job(
                role=j["text"],
                location=(j.get("categories") or {}).get("location", ""),
                link=j["hostedUrl"],
                description=j.get("descriptionPlain", ""),
                external_id=f"lv-{slug}-{j['id']}",
            )
            for j in data
        ]
    if ats == "ashby":
        return [
            job(
                role=j["title"],
                location=j.get("location", ""),
                link=j.get("jobUrl") or j.get("applyUrl", ""),
                description=j.get("descriptionPlain", ""),
                external_id=f"ab-{slug}-{j['id']}",
            )
            for j in data.get("jobs", [])
        ]
    return [  # workable
        job(
            role=j["title"],
            location=", ".join(
                filter(None, [j.get("city"), j.get("country")])
            ),
            link=j.get("url") or j.get("application_url", ""),
            description=_strip_html(j.get("description", "")),
            external_id=f"wk-{slug}-{j.get('shortcode') or j.get('id')}",
        )
        for j in data.get("jobs", [])
    ]
