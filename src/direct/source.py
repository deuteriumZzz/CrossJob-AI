from __future__ import annotations

import re

from src.direct.ats import discover_ats, fetch_jobs
from src.direct.boards import fetch_hn_hiring, fetch_wwr
from src.job import Job
from src.job_sources.blacklist_filter import passes_blacklists
from src.job_sources.preferences import effective_list
from src.logging import logger

# Слова, которые есть почти в любой должности и ничего не говорят о
# специализации — без них "Python-разработчик" сводится к "python".
_GENERIC_WORDS = {
    "developer", "разработчик", "engineer", "инженер", "программист",
    "senior", "middle", "junior", "lead", "specialist", "специалист",
    "remote", "удаленно", "удалённо", "software",
}
_WORD_RE = re.compile(r"[\w+#.]+")


def matches_positions(job: Job, positions: list[str]) -> bool:
    """Все значимые слова хотя бы одной из positions есть в названии.
    ponytail: по словам, без синонимов ("Python" не найдёт "Django-
    разработчик") — расширить positions, если не хватает."""
    if not positions:
        return True
    title = job.role.casefold()
    for position in positions:
        words = [
            w for w in _WORD_RE.findall(position.casefold())
            if w not in _GENERIC_WORDS
        ]
        if words and all(w in title for w in words):
            return True
    return False


class DirectSource:
    """Сайты компаний (direct.companies) + We Work Remotely + Hacker
    News «Who is hiring». Сбой одного источника или компании не
    останавливает остальные."""

    def search(self, preferences: dict) -> list[Job]:
        config = preferences.get("direct") or {}
        jobs: list[Job] = []
        for company in config.get("companies") or []:
            company = dict(company)
            if not company.get("ats") and company.get("website"):
                found = discover_ats(company["website"])
                if found is None:
                    logger.warning(
                        f"direct: у {company.get('name')} не нашли ATS на "
                        f"{company['website']} — пропускаю."
                    )
                    continue
                company["ats"], company["slug"] = found
            if not company.get("ats") or not company.get("slug"):
                continue
            company.setdefault("name", company["slug"])
            try:
                jobs.extend(fetch_jobs(company))
            except Exception as e:
                logger.warning(f"direct: {company['name']}: {e}")
        for enabled, fetch, name in (
            (config.get("wwr", True), fetch_wwr, "We Work Remotely"),
            (config.get("hn", True), fetch_hn_hiring, "HN Who is hiring"),
        ):
            if not enabled:
                continue
            try:
                jobs.extend(fetch())
            except Exception as e:
                logger.warning(f"direct: {name}: {e}")

        positions = effective_list(preferences, "direct", "positions")
        return [
            job
            for job in jobs
            if matches_positions(job, positions)
            and passes_blacklists(job, preferences)
        ]
