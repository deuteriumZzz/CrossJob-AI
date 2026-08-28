from src.job import Job
from src.job_sources.blacklist_filter import passes_blacklists
from src.job_sources.careerist.client import CareeristClient
from src.job_sources.careerist.mapping import (
    careerist_vacancy_to_job,
    parse_search_results,
)
from src.job_sources.preferences import effective_list

# ponytail: одна страница /jobs-{query}/ на позицию, без пагинации —
# не подтверждено, поддерживает ли она ?page=; 25-30 вакансий на
# запрос достаточно для старта (тот же компромисс, что у wellfound).


class CareeristSource:
    def __init__(self, client: CareeristClient):
        self.client = client

    def search(self, preferences: dict) -> list[Job]:
        seen_ids: set = set()
        jobs: list[Job] = []

        for position in effective_list(preferences, "careerist", "positions"):
            html = self.client.search_html(position)
            if html is None:
                continue

            for vacancy_id, path in parse_search_results(html):
                if vacancy_id in seen_ids:
                    continue
                seen_ids.add(vacancy_id)

                detail_html = self.client.get_vacancy_html(path)
                job = careerist_vacancy_to_job(detail_html, vacancy_id, path)
                if passes_blacklists(job, preferences):
                    jobs.append(job)

        return jobs
