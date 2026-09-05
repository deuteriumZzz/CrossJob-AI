from bs4 import BeautifulSoup

from src.job import Job
from src.job_sources.html_text import strip_html

HC_BASE_URL = "https://career.habr.com"
REMOTE_LABEL = "Можно удалённо"


def _extract_location(soup: BeautifulSoup) -> str:
    """Подтверждено прямым запросом (2026-09-05) на 2 живых вакансиях:
    блок "Условия" (.vacancy-meta) содержит один чип с иконкой формата
    работы (svg-icon--icon-format -> "Можно удалённо") ЛИБО с иконкой
    геометки (svg-icon--icon-placemark -> название города, например
    "Новосибирск"). Тот же класс .vacancy-meta есть и у блока
    "Требования" (роль/грейд/навыки) — поэтому матчим по классу иконки,
    а не по позиции чипа. Если чипов формата/локации нет вообще —
    вакансия без пометки, возвращаем ''."""
    location = ""
    for icon in soup.select(".vacancy-meta svg.svg-icon"):
        classes = icon.get("class") or []
        chip = icon.find_parent(class_="basic-chip")
        text_el = chip.select_one(".chip-with-icon__text") if chip else None
        text = text_el.get_text(strip=True) if text_el else ""
        if any("icon-format" in c for c in classes):
            return text or REMOTE_LABEL
        if any("icon-placemark" in c for c in classes):
            location = text
    return location


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
    нет). location — см. docstring _extract_location. apply_method всегда
    "habr_career_manual" — отклик требует входа через SSO Хабра, см.
    client.py."""
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
        location=_extract_location(soup),
        link=f"{HC_BASE_URL}/vacancies/{vacancy_id}",
        description=strip_html(str(description)) if description else "",
        source="habr_career",
        external_id=vacancy_id,
        apply_method="habr_career_manual",
        salary=salary.get_text(strip=True) if salary else "",
    )
