import itertools
from typing import Optional

from src.job import Job
from src.job_sources.applied_log import max_new_per_run, seen_ids_for
from src.job_sources.blacklist_filter import passes_blacklists
from src.job_sources.block_detection import PlatformBlockedError
from src.job_sources.filters import habr_qualifications
from src.job_sources.filters import remote_only as remote_only_filter
from src.job_sources.filters import single_employment
from src.job_sources.habr_career.client import HabrCareerClient
from src.job_sources.habr_career.mapping import (
    habr_vacancy_to_job,
    parse_search_results,
)
from src.job_sources.preferences import effective_list
from src.logging import logger

# ponytail: одна страница /vacancies?q=... на позицию, без пагинации —
# ?page= поддерживается сайтом, но не подключён здесь: 20-25 вакансий
# на запрос достаточно для старта.


class HabrCareerSource:
    def __init__(self, client: HabrCareerClient):
        self.client = client

    def search(self, preferences: dict) -> list[Job]:
        hc_preferences = preferences.get("habr_career") or {}
        remote_only = remote_only_filter(preferences, "habr_career")
        qualification = hc_preferences.get("qualification") or None
        employment_type = (
            single_employment(preferences)
            or hc_preferences.get("employment_type")
            or None
        )

        seen_ids: set = set()
        already_seen = seen_ids_for(preferences, "habr_career")
        max_new = max_new_per_run(preferences, "habr_career")
        opened = 0
        jobs: list[Job] = []

        # Общие «Уровни» («Что ищу»): Habr принимает один уровень за запрос —
        # ищем по каждому выбранному (дешёвый HTTP). Не выбраны — своя
        # настройка площадки.
        qualifications: list[Optional[str]] = [
            *habr_qualifications(preferences)
        ] or [qualification]
        for position, qualification in itertools.product(
            effective_list(preferences, "habr_career", "positions"),
            qualifications,
        ):
            # ponytail: тот же краш посреди прогона, что чинили у
            # GeekjobSource/GetMatchSource — Chrome может умереть между
            # вызовами клиента и вылететь исключением наружу вместо
            # того, чтобы дать _acquire_driver пересоздать драйвер на
            # следующем вызове.
            try:
                html = self.client.search_html(
                    position,
                    remote_only=remote_only,
                    qualification=qualification,
                    employment_type=employment_type,
                    only_with_salary=bool(preferences.get("only_with_salary")),
                )
            except PlatformBlockedError:
                raise
            except Exception as e:
                logger.exception(
                    f"habr.career поиск упал на '{position}' — "
                    f"пропускаю, продолжаю со следующей позицией: {e}"
                )
                continue

            for vacancy_id in parse_search_results(html):
                if vacancy_id in seen_ids:
                    continue
                seen_ids.add(vacancy_id)
                if vacancy_id in already_seen:
                    continue  # уже в журнале — страницу не открываем
                if opened >= max_new:
                    return jobs
                opened += 1

                try:
                    detail_html = self.client.get_vacancy_html(vacancy_id)
                except PlatformBlockedError:
                    raise
                except Exception as e:
                    logger.exception(
                        f"habr.career вакансия {vacancy_id} упала — "
                        f"пропускаю, продолжаю: {e}"
                    )
                    continue
                job = habr_vacancy_to_job(detail_html, vacancy_id)
                if passes_blacklists(job, preferences):
                    jobs.append(job)

        return jobs
