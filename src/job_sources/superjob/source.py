from __future__ import annotations

import httpx

from src.job import Job
from src.job_sources.blacklist_filter import passes_blacklists
from src.job_sources.preferences import effective_list
from src.job_sources.html_text import strip_html
from src.job_sources.superjob.client import SuperJobClient
from src.job_sources.superjob.mapping import sj_vacancy_to_job
from src.logging import logger

# ponytail: фиксированный размер страницы вместо полной пагинации,
# увеличить, если 20 вакансий на должность перестанет хватать.
RESULTS_PER_POSITION = 20

# ponytail: числовые перечисления SuperJob для period/experience/
# type_of_work не проверены на живом API (в отличие от HH, где они
# хорошо известны), поэтому на сервер уходит только свободнотекстовый
# поиск `keyword`. Вся остальная фильтрация (чёрные списки, локации)
# происходит на клиенте через passes_blacklists, как и у HH. Добавить
# параметры period/experience/employment, как только они будут
# подтверждены на реальном приложении SuperJob.


def _with_company_description(
    job: Job, detail: dict, client: SuperJobClient
) -> Job:
    """Приблизительно: добавляет к описанию вакансии официальное
    описание работодателя из профиля SuperJob. Неудачный запрос не
    должен прерывать весь поиск."""
    employer_id = (detail.get("client") or {}).get("id")
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
    return job


class SuperJobSource:
    def __init__(self, client: SuperJobClient):
        self.client = client

    def search(self, preferences: dict) -> list[Job]:
        seen_ids: set[str] = set()
        jobs: list[Job] = []

        for position in effective_list(preferences, "superjob", "positions"):
            results = self.client.search_vacancies(
                {"keyword": position, "count": RESULTS_PER_POSITION}
            )
            for item in results.get("objects", []):
                vacancy_id = str(item["id"])
                if vacancy_id in seen_ids:
                    continue
                seen_ids.add(vacancy_id)

                detail = self.client.get_vacancy(vacancy_id)
                job = sj_vacancy_to_job(detail)
                if not passes_blacklists(job, preferences):
                    continue

                jobs.append(
                    _with_company_description(job, detail, self.client)
                )

        return jobs
