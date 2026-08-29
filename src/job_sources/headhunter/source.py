from __future__ import annotations

from typing import Protocol

import httpx

from src.job import Job
from src.job_sources.blacklist_filter import passes_blacklists
from src.job_sources.headhunter.client import HeadHunterClient
from src.job_sources.headhunter.mapping import hh_vacancy_to_job
from src.job_sources.html_text import strip_html
from src.job_sources.preferences import effective_list
from src.logging import logger


class _EmployerLookupClient(Protocol):
    """Структурный тип для клиентов с сигнатурой
    get_employer(employer_id) -> dict."""

    def get_employer(self, employer_id: str) -> dict: ...


# ponytail: фиксированный размер страницы вместо полной пагинации,
# увеличить, если 20 вакансий на должность перестанет хватать.
RESULTS_PER_POSITION = 20

_PERIOD_DAYS_BY_DATE_FILTER = [
    ("24_hours", 1),
    ("week", 7),
    ("month", 30),
    ("all_time", None),
]

_EXPERIENCE_LEVEL_TO_HH = {
    "internship": "noExperience",
    "entry": "noExperience",
    "associate": "between1And3",
    "mid_senior_level": "between3And6",
    "director": "moreThan6",
    "executive": "moreThan6",
}

_JOB_TYPE_TO_HH_EMPLOYMENT = {
    "full_time": "full",
    "part_time": "part",
    "volunteer": "volunteer",
}


def _period_days(date_filters: dict) -> int | None:
    for key, days in _PERIOD_DAYS_BY_DATE_FILTER:
        if date_filters.get(key):
            return days
    return None


def _hh_experience_values(experience_level: dict) -> list[str]:
    values = {
        _EXPERIENCE_LEVEL_TO_HH[level]
        for level, enabled in experience_level.items()
        if enabled and level in _EXPERIENCE_LEVEL_TO_HH
    }
    return sorted(values)


def _hh_employment_values(job_types: dict) -> list[str]:
    return sorted(
        {
            _JOB_TYPE_TO_HH_EMPLOYMENT[job_type]
            for job_type, enabled in job_types.items()
            if enabled and job_type in _JOB_TYPE_TO_HH_EMPLOYMENT
        }
    )


def _build_search_params(preferences: dict, text: str) -> dict:
    params: dict = {"text": text, "per_page": RESULTS_PER_POSITION}

    period = _period_days(preferences.get("date", {}))
    if period is not None:
        params["period"] = period

    experience_values = _hh_experience_values(
        preferences.get("experience_level", {})
    )
    if experience_values:
        params["experience"] = experience_values

    employment_values = _hh_employment_values(preferences.get("job_types", {}))
    if employment_values:
        params["employment"] = employment_values

    if (
        preferences.get("remote")
        and not preferences.get("hybrid")
        and not preferences.get("onsite")
    ):
        params["schedule"] = "remote"

    return params


def _with_company_description(
    job: Job, detail: dict, client: _EmployerLookupClient
) -> Job:
    """Приблизительно: добавляет к описанию вакансии официальное описание
    работодателя из профиля HH — для более информированного
    сопроводительного письма. Неудачный запрос не должен прерывать весь
    поиск."""
    employer_id = (detail.get("employer") or {}).get("id")
    if not employer_id:
        return job
    try:
        employer = client.get_employer(employer_id)
    except httpx.HTTPError as e:
        logger.debug(f"Could not fetch employer {employer_id} info: {e}")
        return job

    company_description = strip_html(employer.get("description") or "")
    if company_description:
        job.description = (
            f"{job.description}\n\nО компании:\n{company_description}"
        )
    job.company_url = (
        employer.get("site_url") or employer.get("alternate_url") or ""
    )
    return job


class HeadHunterSource:
    def __init__(self, client: HeadHunterClient):
        self.client = client

    def search(self, preferences: dict) -> list[Job]:
        seen_ids: set[str] = set()
        jobs: list[Job] = []

        for position in effective_list(preferences, "headhunter", "positions"):
            params = _build_search_params(preferences, text=position)
            results = self.client.search_vacancies(params)
            for item in results.get("items", []):
                vacancy_id = str(item["id"])
                if vacancy_id in seen_ids:
                    continue
                seen_ids.add(vacancy_id)

                detail = self.client.get_vacancy(vacancy_id)
                job = hh_vacancy_to_job(detail)
                if not passes_blacklists(job, preferences):
                    continue

                jobs.append(
                    _with_company_description(job, detail, self.client)
                )

        return jobs
