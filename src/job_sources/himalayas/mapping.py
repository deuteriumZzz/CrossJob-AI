from __future__ import annotations

import re

from bs4 import BeautifulSoup

from src.job import Job

_JOB_LINK_RE = re.compile(r"^/companies/([a-z0-9-]+)/jobs/([a-z0-9-]+)$")
_COMPANY_LINK_RE = re.compile(r"^/companies/([a-z0-9-]+)$")
_GENERIC_LINK_TEXT = {"view job", "sign up to save this job"}


def _parse_article(article) -> Job | None:
    job_href = None
    title = ""
    for anchor in article.find_all("a", href=True):
        if not _JOB_LINK_RE.match(anchor["href"]):
            continue
        if job_href is None:
            job_href = anchor["href"]
        if title:
            continue
        text = anchor.get_text(strip=True)
        if text and text.lower() not in _GENERIC_LINK_TEXT:
            title = text

    if not job_href or not title:
        return None
    job_match = _JOB_LINK_RE.match(job_href)
    if job_match is None:
        return None
    company_slug, job_slug = job_match.groups()

    company = company_slug.replace("-", " ").title()
    for anchor in article.find_all("a", href=True):
        match = _COMPANY_LINK_RE.match(anchor["href"])
        if match and match.group(1) == company_slug:
            text = anchor.get_text(strip=True)
            if text:
                company = text
            break

    location = ""
    flag = article.find(attrs={"data-testid": "circle-country-flag"})
    if flag and flag.parent:
        location = flag.parent.get_text(strip=True)

    return Job(
        role=title,
        company=company,
        location=location,
        link=f"https://himalayas.app{job_href}",
        description="",
        source="himalayas",
        external_id=f"{company_slug}/{job_slug}",
        apply_method="himalayas_manual",
    )


def parse_search_html(html: str) -> list[Job]:
    """Подтверждено вживую 2026-09-02 на реальном залогиненном аккаунте
    (первый прогон нашёл 20 вакансий) — но изначально role всегда
    оказывался "View job": на каждой карточке ДВЕ ссылки с одинаковым
    href — невидимый оверлей на всю карточку (текст только для
    скринридера "View job", идёт первым в DOM) и отдельная ссылка на
    заголовок с реальным текстом вакансии. Карточка — <article>; внутри
    неё берём первую НЕ-generic подпись среди ссылок на вакансию как
    заголовок, имя компании — из отдельной ссылки "/companies/{slug}"
    (без /jobs/...), локацию — из текста рядом с иконкой флага страны
    (data-testid="circle-country-flag")."""
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[Job] = []
    seen_ids: set = set()

    for article in soup.find_all("article"):
        job = _parse_article(article)
        if job is None or job.external_id in seen_ids:
            continue
        seen_ids.add(job.external_id)
        jobs.append(job)

    return jobs
