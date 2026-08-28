from src.job import Job
from src.job_sources.blacklist_filter import passes_blacklists
from src.job_sources.habr_career.client import HabrCareerClient
from src.job_sources.habr_career.mapping import (
    habr_vacancy_to_job,
    parse_search_results,
)
from src.job_sources.preferences import effective_list

# ponytail: одна страница /vacancies?q=... на позицию, без пагинации —
# ?page= поддерживается сайтом, но не подключён здесь: 20-25 вакансий
# на запрос достаточно для старта (тот же компромисс, что у wellfound/
# careerist).


class HabrCareerSource:
    def __init__(self, client: HabrCareerClient):
        self.client = client

    def search(self, preferences: dict) -> list[Job]:
        seen_ids: set = set()
        jobs: list[Job] = []

        for position in effective_list(
            preferences, "habr_career", "positions"
        ):
            html = self.client.search_html(position)

            for vacancy_id in parse_search_results(html):
                if vacancy_id in seen_ids:
                    continue
                seen_ids.add(vacancy_id)

                detail_html = self.client.get_vacancy_html(vacancy_id)
                job = habr_vacancy_to_job(detail_html, vacancy_id)
                if passes_blacklists(job, preferences):
                    jobs.append(job)

        return jobs
