from src.job_sources.getmatch.mapping import parse_search_results

SEARCH_HTML = """
<div class="b-vacancy-card">
  <div class="b-vacancy-card-title">
    <h3><a href="/vacancies/31449-senior-nlp-specialist?s=offers"
    target="_blank">Senior NLP Specialist</a></h3>
    <h4>в <a href="/companies/GNRXrNQz-sber?s=offers">Сбер</a></h4>
  </div>
  <div class="b-vacancy-locations"><span>📍 Москва</span>
  <span>Гибрид</span></div>
  <div class="b-vacancy-card-description">
  <p>Что делать: строить пайплайны.</p></div>
</div>
<div class="b-vacancy-card">
  <div class="b-vacancy-card-title">
    <h3><a href="/vacancies/12345-backend-engineer?s=offers"
    target="_blank">Backend Engineer</a></h3>
    <h4>в <a href="/companies/wayfair?s=offers">Wayfair</a></h4>
  </div>
</div>
"""


def test_parse_search_results_maps_fields():
    jobs = parse_search_results(SEARCH_HTML)
    assert len(jobs) == 2

    first = jobs[0]
    assert first.role == "Senior NLP Specialist"
    assert first.company == "Сбер"
    assert first.location == "📍 Москва Гибрид"
    assert (
        first.link
        == "https://getmatch.ru/vacancies/31449-senior-nlp-specialist"
    )
    assert first.source == "getmatch"
    assert first.external_id == "31449"
    assert first.apply_method == "getmatch_manual"
    assert "пайплайны" in first.description


def test_parse_search_results_handles_missing_optional_blocks():
    jobs = parse_search_results(SEARCH_HTML)
    second = jobs[1]
    assert second.company == "Wayfair"
    assert second.location == ""
    assert second.description == ""


if __name__ == "__main__":
    test_parse_search_results_maps_fields()
    test_parse_search_results_handles_missing_optional_blocks()
    print("All tests passed.")
