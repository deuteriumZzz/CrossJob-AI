from __future__ import annotations

from src.job import Job
from src.job_sources.applied_log import seen_ids_for
from src.job_sources.blacklist_filter import passes_blacklists
from src.job_sources.block_detection import PlatformBlockedError
from src.job_sources.preferences import effective_list
from src.job_sources.talanto.client import TalantoClient
from src.job_sources.talanto.selectors import SELECTORS
from src.logging import logger

PAGES_PER_POSITION = 2
# За один ход открываем не больше стольких новых вакансий — остальные
# достанутся следующему ходу (в журнал они не попадают, пока не оценены).
DEFAULT_MAX_NEW_PER_RUN = 30


def talanto_vacancy_to_job(raw: dict, job_id: str) -> Job:
    """raw — {title, company, meta, description} со страницы вакансии."""
    company = (raw.get("company") or "").strip()
    if "•" in company:  # название скрыто платным тарифом
        company = ""
    return Job(
        role=(raw.get("title") or "").strip(),
        company=company,
        description=(raw.get("description") or "").strip(),
        link=f"{SELECTORS.base_url}/jobs/{job_id}",
        source="talanto",
        external_id=job_id,
        location=_location_from_meta(raw.get("meta") or ""),
    )


def _location_from_meta(meta: str) -> str:
    # Строка вида "Полная · Senior · Удалённо · Россия" — после названия.
    for line in meta.splitlines():
        if "·" in line:
            return line.strip()
    return ""


class TalantoSource:
    def __init__(self, client: TalantoClient):
        self.client = client

    def search(self, preferences: dict) -> list[Job]:
        """Свежие вакансии по позициям; страницы уже виденных вакансий не
        открываем (см. AppliedLog.seen_ids)."""
        already_seen = seen_ids_for(preferences, "talanto")
        max_new = int(
            (preferences.get("talanto") or {}).get(
                "max_new_per_run", DEFAULT_MAX_NEW_PER_RUN
            )
        )
        seen: set = set()
        jobs: list[Job] = []
        for position in effective_list(preferences, "talanto", "positions"):
            for page in range(1, PAGES_PER_POSITION + 1):
                try:
                    ids = self.client.search_job_ids(position, page)
                except PlatformBlockedError:
                    raise
                except Exception as e:
                    logger.exception(
                        f"talanto: поиск упал на '{position}' стр.{page}: {e}"
                    )
                    break
                if not ids:
                    break
                for job_id in ids:
                    if len(seen) >= max_new:
                        return jobs
                    if job_id in seen or job_id in already_seen:
                        continue
                    seen.add(job_id)
                    try:
                        raw = self.client.get_vacancy(job_id)
                    except PlatformBlockedError:
                        raise
                    except Exception as e:
                        logger.exception(
                            f"talanto: вакансия {job_id} упала — "
                            f"пропускаю: {e}"
                        )
                        continue
                    job = talanto_vacancy_to_job(raw, job_id)
                    if job.role and passes_blacklists(job, preferences):
                        jobs.append(job)
        return jobs
