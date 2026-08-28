import json
import re

from src.job import Job
from src.job_sources.html_text import strip_html

CR_BASE_URL = "https://careerist.ru"
_VACANCY_LINK_RE = re.compile(
    r'href="https://careerist\.ru(/vakansii/[a-z0-9-]+-(\d+)\.html)"'
)
_LD_JSON_RE = re.compile(
    r'<script type="application/ld\+json">(.*?)</script>', re.S
)


def parse_search_results(html: str) -> list[tuple[str, str]]:
    """(id, path) для каждой карточки на странице /jobs-{query}/ —
    сама карточка не парсится, только ссылка на вакансию; остальные
    поля надёжнее достать со страницы вакансии через schema.org
    JobPosting (см. careerist_vacancy_to_job)."""
    seen: set = set()
    results = []
    for path, vacancy_id in _VACANCY_LINK_RE.findall(html):
        if vacancy_id in seen:
            continue
        seen.add(vacancy_id)
        results.append((vacancy_id, path))
    return results


def careerist_vacancy_to_job(html: str, vacancy_id: str, path: str) -> Job:
    """Подтверждено прямым запросом (2026-08-28): страница вакансии
    отдаёт стандартный <script type="application/ld+json"> с
    schema.org JobPosting. apply_method всегда "careerist_manual" —
    завершить отклик анонимно нельзя (кнопка "ОТПРАВИТЬ РЕЗЮМЕ" ведёт
    на register.html), см. client.py про подтверждённый вход."""
    link = f"{CR_BASE_URL}{path}"
    match = _LD_JSON_RE.search(html)
    if not match:
        return Job(
            link=link,
            source="careerist",
            external_id=vacancy_id,
            apply_method="careerist_manual",
        )

    try:
        data = json.loads(match.group(1))
    except ValueError:
        data = {}

    company = (data.get("hiringOrganization") or {}).get("name", "")
    address = (data.get("jobLocation") or {}).get("address") or {}
    location = ", ".join(
        part
        for part in (
            address.get("addressRegion"),
            address.get("addressLocality"),
        )
        if part
    )

    salary_range = data.get("baseSalary") or {}
    salary_value = salary_range.get("value") or {}
    salary = ""
    if salary_value.get("minValue") and salary_value.get("maxValue"):
        currency = salary_range.get("currency", "")
        salary = (
            f"{salary_value['minValue']:.0f}-{salary_value['maxValue']:.0f} "
            f"{currency}/{salary_value.get('unitText', '').lower()}"
        )

    return Job(
        role=data.get("title", ""),
        company=company,
        location=location,
        link=link,
        description=strip_html(data.get("description", "")),
        source="careerist",
        external_id=vacancy_id,
        apply_method="careerist_manual",
        salary=salary,
    )
