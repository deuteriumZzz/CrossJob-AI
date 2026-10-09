from __future__ import annotations

from src.job import Job
from src.job_sources.applied_log import seen_ids_for
from src.job_sources.blacklist_filter import passes_blacklists
from src.job_sources.block_detection import PlatformBlockedError
from src.job_sources.filters import (
    employment_types,
    posted_too_old,
    work_formats,
)
from src.job_sources.hirify.client import HirifyClient
from src.job_sources.hirify.mapping import parse_job, parse_list
from src.job_sources.preferences import effective_list
from src.logging import logger

PAGES_PER_POSITION = 30  # цикл встаёт на пустой странице
# Без лимита, как у остальных площадок: просмотренные пропускаются, первый
# заход долгий. Задать можно на площадку: max_new_per_run.
DEFAULT_MAX_NEW_PER_RUN = 1_000_000

_EMPLOYMENT = {
    "full": "FULL_TIME",
    "part": "PART_TIME",
    "project": "CONTRACTOR",
    "internship": "INTERN",
}


def matches_filters(meta: dict, preferences: dict) -> bool:
    """Общие фильтры «Что ищу» по данным вакансии: период, формат
    (удалёнка / не удалёнка), тип занятости. Неизвестное не отсекаем."""
    if posted_too_old(meta.get("posted_at", ""), preferences):
        return False
    formats = work_formats(preferences)
    if formats and "remote" not in formats and meta.get("remote"):
        return False  # нужен офис или гибрид, а вакансия удалённая
    if formats == ["remote"] and meta.get("remote") is False:
        return False
    wanted = {_EMPLOYMENT[e] for e in employment_types(preferences)}
    have = set(meta.get("employment") or [])
    return not (wanted and have and not wanted & have)


class HirifySource:
    def __init__(self, client: HirifyClient):
        self.client = client

    def search(self, preferences: dict) -> list[Job]:
        already_seen = seen_ids_for(preferences, "hirify")
        max_new = int(
            (preferences.get("hirify") or {}).get(
                "max_new_per_run", DEFAULT_MAX_NEW_PER_RUN
            )
        )
        seen: set[str] = set()
        opened = 0
        jobs: list[Job] = []
        for position in effective_list(preferences, "hirify", "positions"):
            for page in range(1, PAGES_PER_POSITION + 1):
                try:
                    items = parse_list(self.client.list_html(position, page))
                except PlatformBlockedError:
                    raise
                except Exception as e:
                    logger.warning(
                        f"hirify: поиск «{position}» стр.{page} не удался: {e}"
                    )
                    break
                if not items:
                    break
                for item in items:
                    job_id = item["id"]
                    if job_id in seen or job_id in already_seen:
                        continue
                    seen.add(job_id)
                    if opened >= max_new:
                        return jobs
                    opened += 1
                    try:
                        parsed = parse_job(
                            self.client.job_html(job_id, item["slug"]), job_id
                        )
                    except PlatformBlockedError:
                        raise
                    except Exception as e:
                        logger.warning(f"hirify: вакансия {job_id}: {e}")
                        continue
                    if parsed is None:
                        continue
                    job, meta = parsed
                    job.link = (
                        f"https://hirify.me/jobs/{job_id}-{item['slug']}"
                    )
                    if matches_filters(
                        meta, preferences
                    ) and passes_blacklists(job, preferences):
                        jobs.append(job)
        return jobs
