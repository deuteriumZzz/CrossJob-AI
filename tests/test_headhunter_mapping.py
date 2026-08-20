from src.job_sources.blacklist_filter import passes_blacklists
from src.job_sources.headhunter.mapping import hh_vacancy_to_job
from src.job_sources.headhunter.source import (
    _build_search_params,
    _hh_employment_values,
    _hh_experience_values,
    _period_days,
)


def test_hh_vacancy_to_job_maps_fields():
    raw = {
        "id": 12345678,
        "name": "Backend Developer",
        "employer": {"name": "Acme LLC"},
        "area": {"name": "Москва"},
        "alternate_url": "https://hh.ru/vacancy/12345678",
        "description": "<p>Нужен <b>питонист</b>.</p>",
    }
    job = hh_vacancy_to_job(raw)
    assert job.role == "Backend Developer"
    assert job.company == "Acme LLC"
    assert job.location == "Москва"
    assert job.link == "https://hh.ru/vacancy/12345678"
    assert job.source == "headhunter"
    assert job.external_id == "12345678"
    assert "<" not in job.description
    assert "питонист" in job.description


def test_hh_vacancy_to_job_handles_missing_fields():
    job = hh_vacancy_to_job({"id": 1, "name": "X"})
    assert job.company == ""
    assert job.location == ""
    assert job.description == ""


def test_passes_blacklists_rejects_blacklisted_company():
    job = hh_vacancy_to_job(
        {"id": 1, "name": "Dev", "employer": {"name": "Wayfair"}}
    )
    preferences = {"company_blacklist": ["wayfair"]}
    assert passes_blacklists(job, preferences) is False


def test_passes_blacklists_accepts_clean_job():
    job = hh_vacancy_to_job(
        {
            "id": 1,
            "name": "Dev",
            "employer": {"name": "Acme"},
            "area": {"name": "Berlin"},
        }
    )
    preferences = {
        "company_blacklist": [],
        "title_blacklist": [],
        "location_blacklist": [],
        "locations": [],
    }
    assert passes_blacklists(job, preferences) is True


def test_passes_blacklists_filters_by_locations_allowlist():
    job = hh_vacancy_to_job(
        {"id": 1, "name": "Dev", "area": {"name": "Brazil"}}
    )
    preferences = {"locations": ["Germany"]}
    assert passes_blacklists(job, preferences) is False


def test_hh_experience_values_maps_enabled_levels():
    experience_level = {"entry": True, "associate": False, "director": True}
    assert _hh_experience_values(experience_level) == sorted(
        {"noExperience", "moreThan6"}
    )


def test_hh_employment_values_maps_known_job_types_only():
    # У "contract" нет прямого аналога в HH, поэтому смапится
    # только full_time.
    job_types = {"full_time": True, "contract": True, "part_time": False}
    assert _hh_employment_values(job_types) == ["full"]


def test_period_days_prefers_shortest_enabled_window():
    assert _period_days({"all_time": True, "week": True}) == 7
    assert _period_days({"all_time": True}) is None
    assert _period_days({}) is None


def test_build_search_params_sets_remote_schedule_only_when_remote_only():
    preferences = {
        "remote": True,
        "hybrid": False,
        "onsite": False,
        "date": {},
        "experience_level": {},
        "job_types": {},
    }
    params = _build_search_params(preferences, text="Software engineer")
    assert params["schedule"] == "remote"

    preferences_mixed = {**preferences, "hybrid": True}
    params_mixed = _build_search_params(
        preferences_mixed, text="Software engineer"
    )
    assert "schedule" not in params_mixed


if __name__ == "__main__":
    test_hh_vacancy_to_job_maps_fields()
    test_hh_vacancy_to_job_handles_missing_fields()
    test_passes_blacklists_rejects_blacklisted_company()
    test_passes_blacklists_accepts_clean_job()
    test_passes_blacklists_filters_by_locations_allowlist()
    test_hh_experience_values_maps_enabled_levels()
    test_hh_employment_values_maps_known_job_types_only()
    test_period_days_prefers_shortest_enabled_window()
    test_build_search_params_sets_remote_schedule_only_when_remote_only()
    print("All tests passed.")
