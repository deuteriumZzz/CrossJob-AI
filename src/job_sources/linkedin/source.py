from src.job import Job
from src.job_sources.blacklist_filter import passes_blacklists
from src.job_sources.linkedin.search import (
    load_job_description,
    search_easy_apply_jobs,
)


class LinkedInSource:
    def __init__(self, driver):
        self.driver = driver

    def search(self, preferences: dict) -> list[Job]:
        linkedin_preferences = preferences.get("linkedin") or {}
        location = linkedin_preferences.get("location", "")

        seen_ids: set = set()
        jobs: list[Job] = []
        for position in preferences.get("positions", []):
            for job in search_easy_apply_jobs(self.driver, position, location):
                if job.external_id in seen_ids:
                    continue
                seen_ids.add(job.external_id)
                if passes_blacklists(job, preferences):
                    jobs.append(load_job_description(self.driver, job))

        return jobs
