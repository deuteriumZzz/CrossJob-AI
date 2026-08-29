from src.job import Job
from src.job_sources.blacklist_filter import passes_blacklists
from src.job_sources.getmatch.client import GetMatchClient
from src.job_sources.getmatch.mapping import parse_search_results
from src.job_sources.preferences import effective_list

# Сам поиск живёт здесь; реальный клик "Откликнуться" — в
# GetMatchClient.apply() (main.py вызывает его при auto_apply: true),
# подтверждён на живом аккаунте. Сопроводительное письмо генерируется
# для истории отклика, но никуда на самом GetMatch не вставляется —
# сайт нигде его не показывает.


class GetMatchSource:
    def __init__(self, client: GetMatchClient):
        self.client = client

    def search(self, preferences: dict) -> list[Job]:
        seen_ids: set = set()
        jobs: list[Job] = []

        for position in effective_list(preferences, "getmatch", "positions"):
            html = self.client.search_vacancies_html(position)
            for job in parse_search_results(html):
                if job.external_id in seen_ids:
                    continue
                seen_ids.add(job.external_id)
                if passes_blacklists(job, preferences):
                    jobs.append(job)

        return jobs
