from bs4 import BeautifulSoup

from src.job import Job
from src.job_sources.html_text import strip_html

HC_BASE_URL = "https://career.habr.com"


def parse_search_results(html: str) -> list[str]:
    """id вакансий с /vacancies?q=... — карточка отдаёт достаточно
    для дедупликации (ссылка), остальные поля надёжнее взять со
    страницы вакансии (см. habr_vacancy_to_job)."""
    soup = BeautifulSoup(html, "html.parser")
    seen: set = set()
    results = []
    for link in soup.select("a.vacancy-card__backdrop-link[href]"):
        href = str(link.get("href", ""))
        if not href.startswith("/vacancies/"):
            continue
        vacancy_id = href.removeprefix("/vacancies/")
        if vacancy_id in seen:
            continue
        seen.add(vacancy_id)
        results.append(vacancy_id)
    return results


def habr_vacancy_to_job(html: str, vacancy_id: str) -> Job:
    """Подтверждено прямым запросом (2026-08-28): .vacancy-header__title/
    .vacancy-company__title/.vacancy-header__salary/.vacancy-description__text
    — стабильные CSS-классы разметки career.habr.com (JSON-LD на странице
    нет). apply_method всегда "habr_career_manual" — отклик требует
    входа через SSO Хабра, см. client.py."""
    soup = BeautifulSoup(html, "html.parser")

    title = soup.select_one(".vacancy-header__title .page-title__title")
    company = soup.select_one(".vacancy-company__title")
    salary = soup.select_one(
        ".vacancy-header__salary .predicted-salary__title"
    )
    description = soup.select_one(".vacancy-description__text")

    return Job(
        role=title.get_text(strip=True) if title else "",
        company=company.get_text(strip=True) if company else "",
        location="",
        link=f"{HC_BASE_URL}/vacancies/{vacancy_id}",
        description=strip_html(str(description)) if description else "",
        source="habr_career",
        external_id=vacancy_id,
        apply_method="habr_career_manual",
        salary=salary.get_text(strip=True) if salary else "",
    )
