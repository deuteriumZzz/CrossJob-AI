from src.job_sources.rabota_ru.mapping import (
    parse_search_results,
    rabota_ru_vacancy_to_job,
)

SEARCH_HTML = """
<article itemscope itemtype="http://schema.org/JobPosting">
  <h3 itemprop="title">
  <a href="/vacancy/111/?search_id=abc">Python разработчик</a></h3>
</article>
<article itemscope itemtype="http://schema.org/JobPosting">
  <h3 itemprop="title">
  <a href="/vacancy/222/?search_id=abc">Backend Engineer</a></h3>
</article>
"""

VACANCY_HTML = """
<article itemscope itemtype="http://schema.org/JobPosting">
  <h1 itemprop="title">Python разработчик</h1>
  <div itemprop="hiringOrganization" itemscope
    itemtype="http://schema.org/Organization">
    <span itemprop="name">Acme LLC</span>
  </div>
  <div itemprop="jobLocation">Москва</div>
  <div itemprop="description"><p>Нужен <b>питонист</b>.</p></div>
</article>
"""


def test_parse_search_results_extracts_id_and_title():
    results = parse_search_results(SEARCH_HTML)
    assert results == [
        {"id": "111", "title": "Python разработчик"},
        {"id": "222", "title": "Backend Engineer"},
    ]


def test_rabota_ru_vacancy_to_job_maps_fields():
    job = rabota_ru_vacancy_to_job(VACANCY_HTML, "111")
    assert job.role == "Python разработчик"
    assert job.company == "Acme LLC"
    assert job.location == "Москва"
    assert job.link == "https://rabota.ru/vacancy/111/"
    assert job.source == "rabota_ru"
    assert job.external_id == "111"
    assert job.apply_method == "rabota_ru_manual"
    assert "питонист" in job.description
    assert "<" not in job.description


if __name__ == "__main__":
    test_parse_search_results_extracts_id_and_title()
    test_rabota_ru_vacancy_to_job_maps_fields()
    print("All tests passed.")
