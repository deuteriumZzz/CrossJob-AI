from unittest.mock import MagicMock

from src.job_sources.getmatch.mapping import parse_search_results
from src.job_sources.getmatch.source import GetMatchSource

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


def _one_page_client(html: str) -> MagicMock:
    """Мок клиента, отдающий `html` на странице 1 и пустую страницу
    дальше — останавливает пагинацию GetMatchSource.search() так же,
    как это делает сам сайт (см. MAX_PAGES/p=10 в source.py)."""
    client = MagicMock()
    client.search_vacancies_html.side_effect = [html, ""]
    return client


def test_source_search_filters_by_position_keyword():
    """GetMatch убрал ?q= — сайт теперь всегда отдаёт один и тот же
    список независимо от запроса, фильтр по positions делается здесь,
    на нашей стороне (см. ponytail-комментарий в source.py)."""
    client = _one_page_client(SEARCH_HTML)
    source = GetMatchSource(client)

    jobs = source.search({"getmatch": {"positions": ["backend"]}})

    assert [j.role for j in jobs] == ["Backend Engineer"]
    client.search_vacancies_html.assert_called_with(page=2, specializations=[])


def test_source_search_ignores_generic_role_word_and_separator():
    """Полнофразовое совпадение живьую нашло 0 вакансий: "Python
    разработчик" (пробел) не входит подстрокой в "Python-разработчик"
    (дефис) или "Python Developer" (по-английски) — родовое слово
    "разработчик"/"developer" отбрасывается, матчим по "python"."""
    client = _one_page_client(
        SEARCH_HTML
        + """
<div class="b-vacancy-card">
  <div class="b-vacancy-card-title">
    <h3><a href="/vacancies/999-python-razrabotchik?s=offers"
    target="_blank">Python-разработчик</a></h3>
  </div>
</div>
"""
    )
    source = GetMatchSource(client)

    jobs = source.search({"getmatch": {"positions": ["Python разработчик"]}})

    assert [j.role for j in jobs] == ["Python-разработчик"]


def test_source_search_without_positions_returns_everything():
    client = _one_page_client(SEARCH_HTML)
    source = GetMatchSource(client)

    jobs = source.search({"getmatch": {"positions": []}})

    assert len(jobs) == 2


def test_source_search_with_specializations_skips_keyword_filter():
    """specializations задан — сайт уже отфильтровал через sp=
    (чекбоксы "Сфера"), значит "Senior NLP Specialist" (не содержит
    "backend") тоже должен пройти, в отличие от positions-фильтра."""
    client = _one_page_client(SEARCH_HTML)
    source = GetMatchSource(client)

    jobs = source.search(
        {
            "getmatch": {
                "positions": ["backend"],
                "specializations": ["python", "data_science"],
            }
        }
    )

    assert [j.role for j in jobs] == [
        "Senior NLP Specialist",
        "Backend Engineer",
    ]
    client.search_vacancies_html.assert_any_call(
        page=1, specializations=["python", "data_science"]
    )


if __name__ == "__main__":
    test_parse_search_results_maps_fields()
    test_parse_search_results_handles_missing_optional_blocks()
    test_source_search_filters_by_position_keyword()
    test_source_search_ignores_generic_role_word_and_separator()
    test_source_search_without_positions_returns_everything()
    test_source_search_with_specializations_skips_keyword_filter()
    print("All tests passed.")
