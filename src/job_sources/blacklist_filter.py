from src.job import Job


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
    # LinkedIn — исключение: он уже фильтрует по локации на уровне
    # самого поиска (linkedin.locations/geoId в search.py), а job.
    # location там никогда не заполняется (см. search_easy_apply_
    # jobs) — этот же allowlist на LinkedIn проверяет пустую строку
    # против списка русских городов и отбрасывает вообще ВСЕ
    # вакансии до единой (подтверждено живьём: "Found 0 matching" на
    # реальном прогоне, при том что напрямую тот же поиск находил
    # вакансии).
    if job.source != "linkedin":
        locations = preferences.get("locations", [])
        if locations and not matches_any(job.location, locations):
            return False

    return True
