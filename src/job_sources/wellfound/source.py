from src.job import Job
from src.job_sources.blacklist_filter import passes_blacklists
from src.job_sources.preferences import effective_list
from src.job_sources.wellfound.client import WellfoundClient
from src.job_sources.wellfound.mapping import (
    parse_role_page_job_ids,
    wellfound_vacancy_to_job,
)

# ponytail: одна страница /role/... на позицию, без пагинации — сайт
# не подтверждён на предмет ?page=/skip=/take= для этих страниц
# (только для отдельного эндпоинта /api/v1/jobs/similar/{id}), с
# готовой выдачей в 20-50 вакансий на роль этого достаточно для старта.


class WellfoundSource:
    def __init__(self, client: WellfoundClient):
        self.client = client

    def search(self, preferences: dict) -> list[Job]:
        seen_ids: set = set()
        jobs: list[Job] = []

        for position in effective_list(preferences, "wellfound", "positions"):
            html = self.client.search_role_html(position)
            if html is None:
                continue

            for job_id, slug in parse_role_page_job_ids(html):
                if job_id in seen_ids:
                    continue
                seen_ids.add(job_id)

                detail_html = self.client.get_vacancy_html(job_id, slug)
                job = wellfound_vacancy_to_job(detail_html, job_id, slug)
                if passes_blacklists(job, preferences):
                    jobs.append(job)

        return jobs
