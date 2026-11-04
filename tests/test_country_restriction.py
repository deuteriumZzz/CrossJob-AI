from src.job import Job
from src.job_sources.blacklist_filter import passes_blacklists


def job(**kw):
    return Job(role="Python Developer", company="X", **kw)


def test_himalayas_country_list_blocked():
    assert not passes_blacklists(job(location="India", source="himalayas"), {})


def test_himalayas_worldwide_or_empty_passes():
    assert passes_blacklists(job(location="", source="himalayas"), {})
    assert passes_blacklists(job(location="Worldwide", source="himalayas"), {})


def test_text_only_phrase_blocked():
    assert not passes_blacklists(
        job(description="Remote role, India only. Python."), {}
    )
    assert not passes_blacklists(job(description="LATAM-based team"), {})


def test_normal_job_passes():
    assert passes_blacklists(job(description="Remote, work from anywhere"), {})


def test_allowed_country_and_switch():
    prefs = {"remote_allowed_countries": ["India"]}
    assert passes_blacklists(job(location="India", source="himalayas"), prefs)
    assert passes_blacklists(
        job(location="India", source="himalayas"),
        {"country_restriction_filter": False},
    )
