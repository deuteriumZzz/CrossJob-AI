from src.job_sources.blacklist_filter import passes_blacklists
from src.job_sources.superjob.mapping import sj_vacancy_to_job


def test_sj_vacancy_to_job_maps_fields():
    raw = {
        "id": 555,
        "profession": "Python-разработчик",
        "firm_name": "ООО Ромашка",
        "town": {"title": "Москва"},
        "link": "https://www.superjob.ru/vacancy/python-555.html",
        "candidat": "<p>Нужен <b>питонист</b>.</p>",
    }
    job = sj_vacancy_to_job(raw)
    assert job.role == "Python-разработчик"
    assert job.company == "ООО Ромашка"
    assert job.location == "Москва"
    assert job.link == "https://www.superjob.ru/vacancy/python-555.html"
    assert job.source == "superjob"
    assert job.external_id == "555"
    assert "<" not in job.description
    assert "питонист" in job.description


def test_sj_vacancy_to_job_handles_missing_fields():
    job = sj_vacancy_to_job({"id": 1, "profession": "X"})
    assert job.company == ""
    assert job.location == ""
    assert job.description == ""


def test_sj_vacancy_passes_shared_blacklist_filter():
    job = sj_vacancy_to_job(
        {"id": 1, "profession": "Dev", "firm_name": "Wayfair"}
    )
    preferences = {"company_blacklist": ["wayfair"]}
    assert passes_blacklists(job, preferences) is False


if __name__ == "__main__":
    test_sj_vacancy_to_job_maps_fields()
    test_sj_vacancy_to_job_handles_missing_fields()
    test_sj_vacancy_passes_shared_blacklist_filter()
    print("All tests passed.")
