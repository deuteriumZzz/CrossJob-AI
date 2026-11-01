import random
import time

from src.job import Job
from src.job_sources.applied_log import seen_ids_for
from src.job_sources.blacklist_filter import passes_blacklists
from src.job_sources.block_detection import PlatformBlockedError
from src.job_sources.preferences import effective_list
from src.job_sources.wellfound.client import WellfoundClient
from src.job_sources.wellfound.mapping import (
    parse_role_page_job_ids,
    wellfound_vacancy_to_job,
)
from src.logging import logger

# /role/...?page=N подтверждён вживую 1.11 (page=2 — 26 новых id из 28).
ROLE_PAGES = 10
# С пагинацией выдача — сотни вакансий; каждую ещё оценивает ИИ. Без
# предела ход Wellfound шёл десятки минут (1.11), остальные площадки ждали.
DEFAULT_NEW_PER_RUN = 40


class WellfoundSource:
    def __init__(self, client: WellfoundClient):
        self.client = client

    def search(self, preferences: dict) -> list[Job]:
        seen_ids: set = set()
        already_seen = seen_ids_for(preferences, "wellfound")
        max_new = int(
            (preferences.get("wellfound") or {}).get(
                "max_new_per_run", DEFAULT_NEW_PER_RUN
            )
        )
        opened = 0
        jobs: list[Job] = []

        for position in effective_list(preferences, "wellfound", "positions"):
            # Первая страница роли — ~24 давно просмотренных вакансии, и
            # бот неделями находил 0; ?page=2… отдаёт новые (1.11).
            for page in range(1, ROLE_PAGES + 1):
                html = self.client.search_role_html(position, page)
                if html is None:
                    break
                page_ids = [
                    pair
                    for pair in parse_role_page_job_ids(html)
                    if pair[0] not in seen_ids
                ]
                if not page_ids:
                    break
                for job_id, slug in page_ids:
                    if job_id in seen_ids:
                        continue
                    seen_ids.add(job_id)
                    if job_id in already_seen:
                        continue  # уже в журнале — страницу не открываем
                    if opened >= max_new:
                        return jobs
                    opened += 1

                    time.sleep(random.uniform(1.0, 2.5))  # вежливо к сайту
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
