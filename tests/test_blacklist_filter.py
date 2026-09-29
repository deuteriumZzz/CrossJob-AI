from src.job import Job
from src.job_sources.blacklist_filter import passes_blacklists


def test_title_blacklist_checks_description_not_only_role():
    """Некоторые нежелательные вакансии (военные контракты и т.п.) не
    называют это в заголовке — слово всплывает только в описании."""
    job = Job(
        role="Инженер-программист",
        company="Acme",
        description="Служба по контракту от Мин. Обороны РФ.",
        source="avito",
    )
    assert not passes_blacklists(
        job, {"title_blacklist": ["служба по контракту"]}
    )


def test_title_blacklist_still_matches_role():
    job = Job(role="Военный инженер БПЛА", company="Acme", source="avito")
    assert not passes_blacklists(job, {"title_blacklist": ["бпла"]})


def test_title_blacklist_case_insensitive_for_ru_and_en():
    job_ru = Job(role="Junior разработчик", company="Acme", source="avito")
    job_en = Job(role="Junior Developer", company="Acme", source="avito")
    assert not passes_blacklists(job_ru, {"title_blacklist": ["junior"]})
    assert not passes_blacklists(job_en, {"title_blacklist": ["junior"]})


def test_locations_allowlist_does_not_zero_out_sources_without_location():
    """telegram never populates job.location (see blacklist_filter.py) —
    a locations allowlist must not silently drop every vacancy from
    this source, the exact "Found 0" bug already fixed for
    linkedin/himalayas."""
    job = Job(role="Python", company="Acme", location="", source="telegram")
    assert passes_blacklists(job, {"locations": ["Москва"]})


def test_locations_allowlist_still_filters_sources_with_location():
    job = Job(
        role="Python", company="Acme", location="Тбилиси", source="geekjob"
    )
    assert not passes_blacklists(job, {"locations": ["Москва"]})

    job.location = "Москва"
    assert passes_blacklists(job, {"locations": ["Москва"]})


def test_habr_career_locations_allowlist_lets_remote_through():
    """habr_career now parses location (see _extract_location in
    habr_career/mapping.py) — a locations allowlist should still let
    remote vacancies through regardless of city, and still filter out
    non-matching office vacancies."""
    remote_job = Job(
        role="Python",
        company="Acme",
        location="Можно удалённо",
        source="habr_career",
    )
    assert passes_blacklists(remote_job, {"locations": ["Москва"]})

    office_job = Job(
        role="Python",
        company="Acme",
        location="Новосибирск",
        source="habr_career",
    )
    assert not passes_blacklists(office_job, {"locations": ["Москва"]})

    office_job.location = "Москва"
    assert passes_blacklists(office_job, {"locations": ["Москва"]})


def demo() -> None:
    test_locations_allowlist_does_not_zero_out_sources_without_location()
    test_locations_allowlist_still_filters_sources_with_location()
    test_habr_career_locations_allowlist_lets_remote_through()
    print("ok")


if __name__ == "__main__":
    demo()
