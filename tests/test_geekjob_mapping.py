from src.job_sources.geekjob.mapping import (
    geekjob_vacancy_to_job,
    parse_search_results,
)

SEARCH_HTML = """
<ul class="collection serp-list" id="serplist">
  <li class="collection-item avatar ">
    <div class="info"><a href="/vacancy/abc123" target="_blank">Москва<br>
    <span class="salary">до 300K</span></a></div>
    <p class="truncate vacancy-name">
    <a href="/vacancy/abc123" class="title"
    target="_blank">Python разработчик</a></p>
    <p class="truncate company-name">
    <a href="/vacancy/abc123" target="_blank"> Acme LLC</a></p>
  </li>
  <li class="collection-item avatar ">
    <p class="truncate vacancy-name">
    <a href="/vacancy/def456" class="title"
    target="_blank">Backend Engineer</a></p>
    <p class="truncate company-name">
    <a href="/vacancy/def456" target="_blank"> Wayfair</a></p>
  </li>
</ul>
"""

VACANCY_HTML = """
<header>
  <h1>Python разработчик</h1>
  <h5 class="company-name">Прямой работодатель
  <a href="/company/1">Acme LLC</a></h5>
  <div class="location">Москва</div>
</header>
<div id="vacancy-description"><p>Нужен <b>питонист</b>.</p></div>
"""


def test_parse_search_results_extracts_id_and_title():
    results = parse_search_results(SEARCH_HTML)
    assert results == [
        {"id": "abc123", "title": "Python разработчик"},
        {"id": "def456", "title": "Backend Engineer"},
    ]


def test_geekjob_vacancy_to_job_maps_fields():
    job = geekjob_vacancy_to_job(VACANCY_HTML, "abc123")
    assert job.role == "Python разработчик"
    assert job.company == "Acme LLC"
    assert job.location == "Москва"
    assert job.link == "https://geekjob.ru/vacancy/abc123"
    assert job.source == "geekjob"
    assert job.external_id == "abc123"
    assert job.apply_method == "geekjob_manual"
    assert "питонист" in job.description
    assert "<" not in job.description


if __name__ == "__main__":
    test_parse_search_results_extracts_id_and_title()
    test_geekjob_vacancy_to_job_maps_fields()
    print("All tests passed.")
