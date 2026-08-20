from src.job_sources.headhunter.mapping import hh_vacancy_to_job


def test_hh_vacancy_to_job_tags_zarplata_source():
    raw = {
        "id": 42,
        "name": "QA инженер",
        "employer": {"name": "ООО Тест"},
        "area": {"name": "Санкт-Петербург"},
        "alternate_url": "https://zarplata.ru/vacancy/42",
        "description": "<p>Требования...</p>",
    }
    job = hh_vacancy_to_job(raw, source="zarplata")
    assert job.source == "zarplata"
    assert job.apply_method == "zarplata_api"
    assert job.role == "QA инженер"
    assert job.company == "ООО Тест"
    assert job.external_id == "42"


def test_hh_vacancy_to_job_default_source_unchanged():
    job = hh_vacancy_to_job({"id": 1, "name": "X"})
    assert job.source == "headhunter"
    assert job.apply_method == "headhunter_api"


if __name__ == "__main__":
    test_hh_vacancy_to_job_tags_zarplata_source()
    test_hh_vacancy_to_job_default_source_unchanged()
    print("All tests passed.")
