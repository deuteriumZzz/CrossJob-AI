from src.job import Job
from src.job_sources.blacklist_filter import passes_blacklists
from src.job_sources.market_stats import (
    extract_skills,
    parse_salary,
    remote_region,
    salary_stats,
    skill_demand,
)


def test_parse_salary_formats():
    assert parse_salary("180 000 —‍ 250 000 ₽/‍мес на руки") == {
        "currency": "RUB", "min": 180000, "max": 250000,
    }
    assert parse_salary("130000-175000 USD/year") == {
        "currency": "USD", "min": 10833, "max": 14583,
    }
    assert parse_salary("от 3 500 до 4 500  $") == {
        "currency": "USD", "min": 3500, "max": 4500,
    }
    assert parse_salary("до 250 000  ₽")["max"] == 250000
    assert parse_salary("Зарплата не указана") is None
    assert parse_salary("") is None


def test_salary_stats_medians_per_currency():
    entries = [
        {"salary": "100 000 — 200 000 ₽"},
        {"salary": "200 000 — 300 000 ₽"},
        {"salary": "300 000 — 400 000 ₽"},
        {"salary": "5000 $"},
        {"salary": ""},
    ]
    assert salary_stats(entries) == [
        {"currency": "RUB", "count": 3, "median_min": 200000, "median_max": 300000},
        {"currency": "USD", "count": 1, "median_min": 5000, "median_max": 5000},
    ]


def test_remote_region():
    assert remote_region("Remote (US only). Must be located in the US.") == "us_only"
    assert remote_region("You must be authorized to work in the United States") == "us_only"
    assert remote_region("Remote - EU only") == "europe_only"
    assert remote_region("Fully remote, work from anywhere") == "global"
    assert remote_region("Remote. We use Python.") is None
    # "us" внутри обычного текста — не ограничение
    assert remote_region("Join us to build the product") is None


def test_extract_skills_and_demand():
    text = "Python, FastAPI, PostgreSQL, Docker, Kubernetes. Опыт с Go. JavaScript welcome"
    skills = extract_skills(text)
    assert {"Python", "FastAPI", "PostgreSQL", "Docker", "Kubernetes", "Go", "JavaScript"} <= set(skills)
    assert "Java" not in skills
    assert "Go" not in extract_skills("go to the office, then go home")

    entries = [
        {"skills": ["Python", "Kubernetes"]},
        {"skills": ["Python"]},
        {"title": "old entry without skills"},
    ]
    demand = skill_demand(entries, "Python, Docker")
    assert demand == [
        {"skill": "Python", "count": 2, "share": 100.0, "in_resume": True},
        {"skill": "Kubernetes", "count": 1, "share": 50.0, "in_resume": False},
    ]


def test_us_only_filtered_by_default_and_configurable():
    job = Job(
        role="Python Dev",
        company="Acme",
        source="linkedin",
        description="Remote, US only",
    )
    assert passes_blacklists(job, {}) is False
    assert passes_blacklists(job, {"excluded_remote_regions": []}) is True
    open_job = Job(role="Python Dev", company="Acme", source="linkedin",
                   description="Remote from anywhere")
    assert passes_blacklists(open_job, {}) is True
