from src.job_sources.habr_career.mapping import (
    habr_vacancy_to_job,
    parse_search_results,
)

SEARCH_HTML = """
<div class="vacancy-card">
  <a class="vacancy-card__backdrop-link" href="/vacancies/111"></a>
  <div class="vacancy-card__title"><a class="vacancy-card__title-link" href="/vacancies/111">Python разработчик</a></div>
</div>
<div class="vacancy-card">
  <a class="vacancy-card__backdrop-link" href="/vacancies/222"></a>
  <div class="vacancy-card__title"><a class="vacancy-card__title-link" href="/vacancies/222">Backend Engineer</a></div>
</div>
<div class="vacancy-card">
  <a class="vacancy-card__backdrop-link" href="/vacancies/111"></a>
</div>
"""

VACANCY_HTML = """
<html><body>
<div class="vacancy-header__title">
  <div class="page-title"><h1 class="page-title__title">Python разработчик</h1></div>
</div>
<div class="vacancy-header__salary">
  <div class="predicted-salary"><h4 class="predicted-salary__title">200 000 - 300 000 RUR</h4></div>
</div>
<div class="vacancy-company">
  <h2 class="vacancy-company__title">Acme LLC</h2>
</div>
<div class="vacancy-description__text"><p>Нужен <b>питонист</b>.</p></div>
</body></html>
"""


def test_parse_search_results_dedupes():
    assert parse_search_results(SEARCH_HTML) == ["111", "222"]


def test_habr_vacancy_to_job_maps_fields():
    job = habr_vacancy_to_job(VACANCY_HTML, "111")
    assert job.role == "Python разработчик"
    assert job.company == "Acme LLC"
    assert job.salary == "200 000 - 300 000 RUR"
    assert job.link == "https://career.habr.com/vacancies/111"
    assert job.source == "habr_career"
    assert job.external_id == "111"
    assert job.apply_method == "habr_career_manual"
    assert "питонист" in job.description
    assert "<" not in job.description


def test_habr_vacancy_to_job_missing_fields_degrades_gracefully():
    job = habr_vacancy_to_job("<html></html>", "111")
    assert job.link == "https://career.habr.com/vacancies/111"
    assert job.source == "habr_career"
    assert job.role == ""


if __name__ == "__main__":
    test_parse_search_results_dedupes()
    test_habr_vacancy_to_job_maps_fields()
    test_habr_vacancy_to_job_missing_fields_degrades_gracefully()
    print("All tests passed.")
