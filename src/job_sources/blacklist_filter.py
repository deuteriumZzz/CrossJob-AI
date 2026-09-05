from src.job import Job
from src.job_sources.preferences import effective_list

# ponytail: подстрочный маркер "удал" вместо точного списка меток —
# сейчас единственный источник, реально размечающий remote в job.location,
# это habr_career (см. REMOTE_LABEL = "Можно удалённо" в habr_career/
# mapping.py), но проверка обобщена на любой источник/язык разметки
# ("remote"), а не привязана к его точной строке — если появится ещё
# один источник с remote-меткой, дублировать этот бай-пас не придётся.
_REMOTE_MARKERS = ("удал", "remote")


def passes_blacklists(job: Job, preferences: dict) -> bool:
    def matches_any(value: str, blacklist: list) -> bool:
        value_lower = value.lower()
        return any(bad.lower() in value_lower for bad in blacklist)

    def is_remote(location: str) -> bool:
        location_lower = location.lower()
        return any(marker in location_lower for marker in _REMOTE_MARKERS)

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
    # анти-бот интерстишл, см. docstring search_jobs) и telegram
    # (посты — свободный текст, структурного поля локации в принципе
    # нет). Для любой из них allowlist проверял бы пустую строку против
    # списка городов и отбрасывал вообще ВСЕ вакансии до единой
    # (подтверждено живьём на LinkedIn: "Found 0 matching" при том, что
    # напрямую тот же поиск находил вакансии) — не рискуем тем же
    # багом на остальных.
    # habr_career теперь размечает location (см. _extract_location в
    # habr_career/mapping.py) — участвует в allowlist на общих
    # основаниях, но remote-вакансии ("Можно удалённо") проходят
    # независимо от списка городов, а не только вакансии в этих
    # городах — пользователь ищет удалёнку + свои города, а не только
    # свои города.
    if job.source not in ("linkedin", "himalayas", "telegram"):
        locations = effective_list(preferences, job.source, "locations")
        if (
            locations
            and not is_remote(job.location)
            and not matches_any(job.location, locations)
        ):
            return False

    return True
