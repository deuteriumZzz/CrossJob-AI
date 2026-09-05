from src.job import Job
from src.job_sources.blacklist_filter import passes_blacklists


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
