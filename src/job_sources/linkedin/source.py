from src.job import Job
from src.job_sources.applied_log import max_new_per_run, seen_ids_for
from src.job_sources.blacklist_filter import passes_blacklists
from src.job_sources.linkedin.search import (
    load_job_description,
    search_easy_apply_jobs,
)
from src.job_sources.preferences import effective_list


class LinkedInSource:
    def __init__(self, driver):
        self.driver = driver

    def search(self, preferences: dict) -> list[Job]:
        linkedin_preferences = preferences.get("linkedin") or {}
        # Список стран, а не одна — кандидат физически не может
        # переехать без визы, поэтому ищем по конкретному набору
        # remote-дружелюбных рынков (то же самое, что уже настроено
        # в Job preferences самого LinkedIn-аккаунта), а не по одной
        # локации и не по всему миру без разбора.
        locations = linkedin_preferences.get("locations") or [""]

        seen_ids: set = set()
        already_seen = seen_ids_for(preferences, "linkedin")
        max_new = max_new_per_run(preferences, "linkedin")
        opened = 0
        jobs: list[Job] = []
        for position in effective_list(preferences, "linkedin", "positions"):
            for location in locations:
                for job in search_easy_apply_jobs(
                    self.driver, position, location
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
