from src.job import Job
from src.job_sources.blacklist_filter import passes_blacklists
from src.job_sources.headhunter.browser_client import HeadHunterBrowserClient
from src.job_sources.headhunter.browser_mapping import (
    hh_html_vacancy_to_job,
    parse_search_results,
)
from src.job_sources.preferences import effective_list

# ponytail: фиксированная неглубокая пагинация (2 страницы на должность)
# вместо обхода всех страниц, увеличить, если это перестанет давать
# достаточно вакансий.
PAGES_PER_POSITION = 2


class HeadHunterBrowserSource:
    def __init__(self, client: HeadHunterBrowserClient):
        self.client = client

    def search(self, preferences: dict) -> list[Job]:
        remote_only = bool(
            preferences.get("remote")
            and not preferences.get("hybrid")
            and not preferences.get("onsite")
        )

        seen_ids: set = set()
        jobs: list[Job] = []

        for position in effective_list(preferences, "headhunter", "positions"):
            for page in range(PAGES_PER_POSITION):
                html = self.client.search_vacancies_html(
                    position, remote_only, page=page
                )
                items = parse_search_results(html)
                if not items:
                    break

                for item in items:
                    if item.external_id in seen_ids:
                        continue
                    seen_ids.add(item.external_id)

                    detail_html = self.client.get_vacancy_html(
                        item.external_id
                    )
                    job = hh_html_vacancy_to_job(detail_html, item.external_id)
                    if not job.role:
                        job = item
                    else:
                        # hh_html_vacancy_to_job не размечает location
                        # (нет проверенного селектора на странице
                        # вакансии) — берём адрес, который уже пришёл
                        # с карточки поиска (vacancy-serp__vacancy-
                        # address, подтверждено живьём), иначе
                        # passes_blacklists всегда режет по пустой
                        # строке против locations-allowlist.
                        job.location = item.location
                    if passes_blacklists(job, preferences):
                        jobs.append(job)

        return jobs
