from src.job import Job
from src.job_sources.preferences import effective_list


def passes_blacklists(job: Job, preferences: dict) -> bool:
    def matches_any(value: str, blacklist: list) -> bool:
        value_lower = value.lower()
        return any(bad.lower() in value_lower for bad in blacklist)

    if matches_any(job.company, preferences.get("company_blacklist", [])):
        return False
    if matches_any(job.role, preferences.get("title_blacklist", [])):
        return False
    if matches_any(job.location, preferences.get("location_blacklist", [])):
        return False

    # locations — общий allowlist для площадок, которые ищут широко
    # (например HH — по всей area=113 "Россия") и полагаются на этот
    # пост-фильтр, чтобы сузить до конкретных городов вроде "Москва".
    # Исключения — площадки, где job.location никогда не заполняется:
    # LinkedIn (фильтрует по локации на уровне самого поиска —
    # linkedin.locations/geoId в search.py, см. search_easy_apply_
    # jobs), himalayas (карточки поиска не подтверждены вживую —
    # анти-бот интерстишл, см. docstring search_jobs), habr_career
    # (habr_vacancy_to_job не размечает location — нет проверенного
    # селектора) и telegram (посты — свободный текст, структурного
    # поля локации в принципе нет). Для любой из них allowlist
    # проверял бы пустую строку против списка городов и отбрасывал
    # вообще ВСЕ вакансии до единой (подтверждено живьём на LinkedIn:
    # "Found 0 matching" при том, что напрямую тот же поиск находил
    # вакансии) — не рискуем тем же багом на остальных трёх.
    if job.source not in ("linkedin", "himalayas", "habr_career", "telegram"):
        locations = effective_list(preferences, job.source, "locations")
        if locations and not matches_any(job.location, locations):
            return False

    return True
