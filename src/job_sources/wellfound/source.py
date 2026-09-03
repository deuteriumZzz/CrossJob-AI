from src.job import Job
from src.job_sources.blacklist_filter import passes_blacklists
from src.job_sources.block_detection import PlatformBlockedError
from src.job_sources.preferences import effective_list
from src.job_sources.wellfound.client import WellfoundClient
from src.job_sources.wellfound.mapping import (
    parse_role_page_job_ids,
    wellfound_vacancy_to_job,
)
from src.logging import logger

# ponytail: одна страница /role/... на позицию, без пагинации — сайт
# не подтверждён на предмет ?page=/skip=/take= для этих страниц, с
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

                try:
                    detail_html = self.client.get_vacancy_html(job_id, slug)
                except PlatformBlockedError:
                    raise
                except Exception as e:
                    # ponytail: та же защита, что уже стоит у
                    # GeekjobSource/HabrCareerSource — вакансия из
                    # выдачи роли могла успеть исчезнуть (сняли/
                    # протухла, 404) до того, как дошли до её страницы.
                    # Раньше это улетало наружу и хоронило весь прогон
                    # площадки вместо одной вакансии.
                    logger.exception(
                        f"wellfound.com вакансия {job_id} упала — "
                        f"пропускаю, продолжаю: {e}"
                    )
                    continue
                job = wellfound_vacancy_to_job(detail_html, job_id, slug)
                if passes_blacklists(job, preferences):
                    jobs.append(job)

        return jobs
