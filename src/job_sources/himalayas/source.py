from src.job import Job
from src.job_sources.blacklist_filter import passes_blacklists
from src.job_sources.himalayas.search import load_job_description, search_jobs
from src.job_sources.preferences import effective_list


class HimalayasSource:
    def __init__(self, driver):
        self.driver = driver

    def search(self, preferences: dict) -> list[Job]:
        seen_ids: set = set()
        jobs: list[Job] = []

        for position in effective_list(preferences, "himalayas", "positions"):
            for job in search_jobs(self.driver, position):
                if job.external_id in seen_ids:
                    continue
                seen_ids.add(job.external_id)
                if passes_blacklists(job, preferences):
                    jobs.append(load_job_description(self.driver, job))

        return jobs
