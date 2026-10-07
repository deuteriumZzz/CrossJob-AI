from src.job_sources.talanto.client import company_from_apply_url
from src.job_sources.talanto.source import talanto_vacancy_to_job


def test_vacancy_dict_becomes_job():
    job = talanto_vacancy_to_job(
        {
            "title": "Python Developer",
            "company": "IQVIA",
            "meta": "46 мин. назад\nPython Developer\nПолная · Kochi, Индия",
            "description": "3-4 years of Python",
        },
        "08c393da-e82e-4f6d-b19a-dc6a31842e88",
    )
    assert job.source == "talanto"
    assert job.company == "IQVIA"
    assert job.link == (
        "https://talanto.work/jobs/08c393da-e82e-4f6d-b19a-dc6a31842e88"
    )
    assert job.location == "Полная · Kochi, Индия"


def test_company_hidden_by_paid_plan_is_dropped():
    job = talanto_vacancy_to_job(
        {"title": "Dev", "company": "•••••••", "description": "x"}, "id"
    )
    assert job.company == ""


def test_company_from_apply_url_uses_domain():
    assert company_from_apply_url("https://jobs.iqvia.com/en/job/1") == "Iqvia"
    assert company_from_apply_url("https://careers.acme.io/x") == "Acme"
    assert company_from_apply_url("") == ""
