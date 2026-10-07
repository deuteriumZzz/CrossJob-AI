from src.job import Job
from src.job_sources.avito.search import search_jobs
from src.job_sources.blacklist_filter import passes_blacklists
from src.job_sources.block_detection import PlatformBlockedError
from src.job_sources.filters import avito_click_format
from src.job_sources.filters import remote_only as remote_only_filter
from src.job_sources.filters import single_employment
from src.job_sources.preferences import effective_list
from src.logging import logger


class AvitoSource:
    def __init__(self, driver):
        self.driver = driver

    def search(self, preferences: dict) -> list[Job]:
        seen_ids: set = set()
        jobs: list[Job] = []
        av_prefs = preferences.get("avito") or {}
        remote_only = remote_only_filter(preferences, "avito")
        # Переиспользует общие поля qualification/employment_type
        # (те же имена и тип — строка, — что уже завёл Habr Career;
        # у Avito "Опыт работы" тоже одиночный выбор, не список, в
        # отличие от experience_level у GetMatch).
        experience_level = av_prefs.get("qualification") or ""
        employment_type = (
            single_employment(preferences)
            or av_prefs.get("employment_type")
            or ""
        )

        for position in effective_list(preferences, "avito", "positions"):
            try:
                found = search_jobs(
                    self.driver,
                    position,
                    remote_only,
                    experience_level,
                    employment_type,
                    avito_click_format(preferences),
                )
            except PlatformBlockedError:
                raise
            except Exception as e:
                # ponytail: та же устойчивость, что у geekjob.search —
                # упавшая позиция (тайм-аут навигации и т.п.) не должна
                # хоронить весь прогон, остальные positions всё равно
                # стоит попробовать.
                logger.exception(
                    f"avito.ru поиск упал на '{position}' — "
                    f"пропускаю, продолжаю со следующей позицией: {e}"
                )
                continue
            for job in found:
                if job.external_id in seen_ids:
                    continue
                seen_ids.add(job.external_id)
                if passes_blacklists(job, preferences):
                    jobs.append(job)

        return jobs
