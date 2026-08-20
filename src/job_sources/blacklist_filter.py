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

    locations = preferences.get("locations", [])
    if locations and not matches_any(job.location, locations):
        return False

    return True
