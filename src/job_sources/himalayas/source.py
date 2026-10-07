from src.job import Job
from src.job_sources.applied_log import max_new_per_run, seen_ids_for
from src.job_sources.blacklist_filter import passes_blacklists
from src.job_sources.filters import himalayas_query
from src.job_sources.himalayas.search import load_job_description, search_jobs
from src.job_sources.preferences import effective_list


class HimalayasSource:
    def __init__(self, driver):
        self.driver = driver

    def search(self, preferences: dict) -> list[Job]:
        seen_ids: set = set()
        already_seen = seen_ids_for(preferences, "himalayas")
        max_new = max_new_per_run(preferences, "himalayas")
        opened = 0
        jobs: list[Job] = []

        for position in effective_list(preferences, "himalayas", "positions"):
            for job in search_jobs(
                self.driver, position, himalayas_query(preferences)
            ):
                if job.external_id in seen_ids:
                    continue
                seen_ids.add(job.external_id)
                if job.external_id in already_seen:
                    continue  # уже в журнале — страницу не открываем
                if opened >= max_new:
                    return jobs
                opened += 1
                if passes_blacklists(job, preferences):
                    jobs.append(load_job_description(self.driver, job))

        return jobs
