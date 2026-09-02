import json
import re

from src.job import Job
from src.job_sources.html_text import strip_html

WF_BASE_URL = "https://wellfound.com"
_JOB_ID_RE = re.compile(r'href="/jobs/(\d+)-([a-z0-9-]+)"')
_LD_JSON_RE = re.compile(
    r'<script type="application/ld\+json">(.*?)</script>', re.S
)


def parse_role_page_job_ids(html: str) -> list[tuple[str, str]]:
    """(id, slug) для каждой карточки на странице /role/... — сама
    карточка (Tailwind-разметка без стабильных классов) не парсится,
    только ссылка на детальную страницу; company/location/salary/
    description надёжно достаются со страницы вакансии через
    schema.org JobPosting (см. wellfound_vacancy_to_job)."""
    seen: set = set()
    results = []
    for job_id, slug in _JOB_ID_RE.findall(html):
        if job_id in seen:
            continue
        seen.add(job_id)
        results.append((job_id, slug))
    return results


def wellfound_vacancy_to_job(html: str, job_id: str, slug: str) -> Job:
    """Подтверждено прямым запросом (2026-09-02): страница вакансии
    отдаёт стандартный <script type="application/ld+json"> с
    schema.org JobPosting — надёжнее, чем Tailwind-классы без
    смысловых имён на остальной странице. apply_method всегда
    "wellfound_manual": реальный apply не проверен на живом
    залогиненном аккаунте, см. client.py."""
    link = f"{WF_BASE_URL}/jobs/{job_id}-{slug}"
    match = _LD_JSON_RE.search(html)
    if not match:
        return Job(
            link=link,
            source="wellfound",
            external_id=job_id,
            apply_method="wellfound_manual",
        )

    try:
        data = json.loads(match.group(1))
    except ValueError:
        data = {}

    company = (data.get("hiringOrganization") or {}).get("name", "")
    company_url = (data.get("hiringOrganization") or {}).get("sameAs", "")
    locations = (data.get("hiringOrganization") or {}).get("location") or []
    location = ""
    if locations:
        address = locations[0].get("address") or {}
        location = ", ".join(
            part
            for part in (
                address.get("addressLocality"),
                address.get("addressCountry"),
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
        source="wellfound",
        external_id=job_id,
        apply_method="wellfound_manual",
        salary=salary,
        company_url=company_url,
    )
