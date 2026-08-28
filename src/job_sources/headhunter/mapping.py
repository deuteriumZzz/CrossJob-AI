from __future__ import annotations

from src.job import Job
from src.job_sources.html_text import strip_html


def _format_salary(salary: dict | None) -> str:
    """Формат {from, to, currency} от HH, схлопнутый в одну строку для отображения."""
    if not salary:
        return ""
    lo, hi = salary.get("from"), salary.get("to")
    currency = salary.get("currency") or ""
    if lo and hi:
        return f"{lo}-{hi} {currency}".strip()
    if lo:
        return f"от {lo} {currency}".strip()
    if hi:
        return f"до {hi} {currency}".strip()
    return ""


def hh_vacancy_to_job(raw: dict, source: str = "headhunter") -> Job:
    """Преобразует ответ GET /vacancies/{id} от api.hh.ru в Job."""
    return Job(
        role=raw.get("name", ""),
        company=(raw.get("employer") or {}).get("name", ""),
        location=(raw.get("area") or {}).get("name", ""),
        link=raw.get("alternate_url", ""),
        description=strip_html(raw.get("description", "")),
        source=source,
        external_id=str(raw.get("id", "")),
        salary=_format_salary(raw.get("salary")),
        apply_method=f"{source}_api",
    )
