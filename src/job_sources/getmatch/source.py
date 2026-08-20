from src.job import Job
from src.job_sources.blacklist_filter import passes_blacklists
from src.job_sources.getmatch.client import GetMatchClient
from src.job_sources.getmatch.mapping import parse_search_results

# Автоматического отклика нет: "Откликнуться" открывает модалку-мастер
# из 5 шагов (подтверждено вождением реального браузера) — уже первый шаг
# спрашивает про формат работы, а дальше почти наверняка требуется вход.
# Угадывать вслепую куда рискованнее, чем простой клик, поэтому только
# поиск, пока реальная залогиненная сессия не подтвердит остальной поток.


class GetMatchSource:
    def __init__(self, client: GetMatchClient):
        self.client = client

    def search(self, preferences: dict) -> list[Job]:
        seen_ids: set = set()
        jobs: list[Job] = []

        for position in preferences.get("positions", []):
            html = self.client.search_vacancies_html(position)
            for job in parse_search_results(html):
                if job.external_id in seen_ids:
                    continue
                seen_ids.add(job.external_id)
                if passes_blacklists(job, preferences):
                    jobs.append(job)

        return jobs
