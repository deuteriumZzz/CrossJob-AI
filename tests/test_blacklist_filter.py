from src.job import Job
from src.job_sources.blacklist_filter import passes_blacklists


def test_locations_allowlist_does_not_zero_out_sources_without_location():
    """habr_career/telegram never populate job.location (see
    blacklist_filter.py) — a locations allowlist must not silently
    drop every vacancy from these sources, the exact "Found 0" bug
    already fixed for linkedin/himalayas."""
    for source in ("habr_career", "telegram"):
        job = Job(role="Python", company="Acme", location="", source=source)
        assert passes_blacklists(job, {"locations": ["Москва"]})


def test_locations_allowlist_still_filters_sources_with_location():
    job = Job(
        role="Python", company="Acme", location="Тбилиси", source="geekjob"
    )
    assert not passes_blacklists(job, {"locations": ["Москва"]})

    job.location = "Москва"
    assert passes_blacklists(job, {"locations": ["Москва"]})


def demo() -> None:
    test_locations_allowlist_does_not_zero_out_sources_without_location()
    test_locations_allowlist_still_filters_sources_with_location()
    print("ok")


if __name__ == "__main__":
    demo()
