from src.job import Job
from src.job_sources.blacklist_filter import passes_blacklists
from src.job_sources.preferences import effective_list
from src.job_sources.rabota_ru.client import RabotaRuClient
from src.job_sources.rabota_ru.mapping import (
    parse_search_results,
    rabota_ru_vacancy_to_job,
)

# ponytail: фиксированная неглубокая пагинация (2 страницы на должность)
# вместо обхода всех страниц, увеличить, если это перестанет давать
# достаточно вакансий.
PAGES_PER_POSITION = 2

# Автоматического отклика здесь нет: действие "Откликнуться" не
# наблюдалось в обычном серверном HTML (в отличие от разметки списка и
# деталей schema.org, которая присутствует и надёжна) — скорее всего,
# оно скрыто за клиентским потоком, требующим входа, как и в случае с
# geekjob.ru. Только поиск, пока реальная залогиненная сессия не
# подтвердит фактический механизм отклика.


class RabotaRuSource:
    def __init__(self, client: RabotaRuClient):
        self.client = client

    def search(self, preferences: dict) -> list[Job]:
        seen_ids: set = set()
        jobs: list[Job] = []

        for position in effective_list(preferences, "rabota_ru", "positions"):
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
                    job = rabota_ru_vacancy_to_job(detail_html, vacancy_id)
                    if passes_blacklists(job, preferences):
                        jobs.append(job)

        return jobs
