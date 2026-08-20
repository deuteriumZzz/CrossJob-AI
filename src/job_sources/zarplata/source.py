from __future__ import annotations

from src.job import Job
from src.job_sources.blacklist_filter import passes_blacklists
from src.job_sources.headhunter.mapping import hh_vacancy_to_job
from src.job_sources.headhunter.source import (
    _build_search_params,
    _with_company_description,
)
from src.job_sources.zarplata.client import ZarplataClient

# Та же платформа HeadHunter-Group, что и hh.ru (см. оговорку в
# client.py), поэтому построение query-параметров и обогащение
# описанием компании применяются как есть.


class ZarplataSource:
    def __init__(self, client: ZarplataClient):
        self.client = client

    def search(self, preferences: dict) -> list[Job]:
        seen_ids: set[str] = set()
        jobs: list[Job] = []

        for position in preferences.get("positions", []):
            params = _build_search_params(preferences, text=position)
            results = self.client.search_vacancies(params)
            for item in results.get("items", []):
                vacancy_id = str(item["id"])
                if vacancy_id in seen_ids:
                    continue
                seen_ids.add(vacancy_id)

                detail = self.client.get_vacancy(vacancy_id)
                job = hh_vacancy_to_job(detail, source="zarplata")
                if not passes_blacklists(job, preferences):
                    continue

                jobs.append(
                    _with_company_description(job, detail, self.client)
                )

        return jobs
