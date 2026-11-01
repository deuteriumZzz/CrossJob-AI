from src.job import Job
from src.job_sources.applied_log import max_new_per_run, seen_ids_for
from src.job_sources.blacklist_filter import passes_blacklists
from src.job_sources.filters import himalayas_query
from src.job_sources.himalayas.search import (
    load_job_description,
    search_jobs,
    search_jobs_api,
)
from src.job_sources.preferences import effective_list
from src.logging import logger

API_PAGES = 10


class HimalayasSource:
    def __init__(self, driver):
        self.driver = driver

    def _batches(self, position: str, preferences: dict):
        """Страницы JSON-API; упал — старая браузерная выдача.
        ponytail: фильтры типа/уровня (himalayas_query) API не передаём —
        параметры его поиска не сверены; режут чёрные списки и оценка."""
        try:
            for page in range(1, API_PAGES + 1):
                batch = search_jobs_api(position, page)
                if not batch:
                    return
                yield batch
        except Exception as e:
            logger.warning(
                f"Himalayas API упал ({e}) — беру выдачу из браузера."
            )
            yield search_jobs(
                self.driver, position, himalayas_query(preferences)
            )

    def search(self, preferences: dict) -> list[Job]:
        seen_ids: set = set()
        already_seen = seen_ids_for(preferences, "himalayas")
        max_new = max_new_per_run(preferences, "himalayas")
        opened = 0
        jobs: list[Job] = []

        for position in effective_list(preferences, "himalayas", "positions"):
            for batch in self._batches(position, preferences):
                for job in batch:
                    if job.external_id in seen_ids:
                        continue
                    seen_ids.add(job.external_id)
                    if job.external_id in already_seen:
                        continue  # уже в журнале — страницу не открываем
                    if opened >= max_new:
                        return jobs
                    opened += 1
                    if passes_blacklists(job, preferences):
                        if not job.description:
                            job = load_job_description(self.driver, job)
                        jobs.append(job)

        return jobs
