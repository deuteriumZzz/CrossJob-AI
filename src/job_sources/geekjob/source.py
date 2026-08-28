from src.job import Job
from src.job_sources.blacklist_filter import passes_blacklists
from src.job_sources.preferences import effective_list
from src.job_sources.geekjob.client import GeekjobClient
from src.job_sources.geekjob.mapping import (
    geekjob_vacancy_to_job,
    parse_search_results,
)

# ponytail: фиксированная неглубокая пагинация (2 страницы на должность)
# вместо обхода всех страниц, увеличить, если это перестанет давать
# достаточно вакансий.
PAGES_PER_POSITION = 2

# Автоотклик есть (geekjob.auto_apply в work_preferences.yaml, см.
# main.py::search_geekjob → GeekjobClient.apply()) — best-effort клик
# по кнопке "Откликнуться" через Selenium, НЕ проверено на живом
# залогиненном аккаунте (вход у geekjob.ru только через OAuth
# соцсетей, см. GeekjobSession — пароль пользователя туда никогда не
# вводится).


class GeekjobSource:
    def __init__(self, client: GeekjobClient):
        self.client = client

    def search(self, preferences: dict) -> list[Job]:
        seen_ids: set = set()
        jobs: list[Job] = []

        for position in effective_list(preferences, "geekjob", "positions"):
            for page in range(1, PAGES_PER_POSITION + 1):
                html = self.client.search_vacancies_html(position, page=page)
                items = parse_search_results(html)
                if not items:
                    break

                for item in items:
                    vacancy_id = item["id"]
                    if vacancy_id in seen_ids:
                        continue
                    seen_ids.add(vacancy_id)

                    detail_html = self.client.get_vacancy_html(vacancy_id)
                    job = geekjob_vacancy_to_job(detail_html, vacancy_id)
                    if passes_blacklists(job, preferences):
                        jobs.append(job)

        return jobs
