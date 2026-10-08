import json
from types import SimpleNamespace

from src.job_sources.headhunter import browser_source
from src.job_sources.headhunter.browser_source import HeadHunterBrowserSource


def test_hh_search_does_not_open_pages_of_vacancies_already_in_log(
    tmp_path, monkeypatch
):
    (tmp_path / "applied_log.json").write_text(
        json.dumps(
            {
                "applications": [
                    {"source": "headhunter", "external_id": "1"},
                    {"source": "linkedin", "external_id": "2"},
                ]
            }
        )
    )
    items = [
        SimpleNamespace(external_id="1", location=""),
        SimpleNamespace(external_id="2", location=""),
    ]
    monkeypatch.setattr(
        browser_source, "parse_search_results", lambda html: items
    )
    monkeypatch.setattr(
        browser_source,
        "hh_html_vacancy_to_job",
        lambda html, vid: SimpleNamespace(role=f"r{vid}", location=""),
    )
    monkeypatch.setattr(browser_source, "passes_blacklists", lambda j, p: True)
    opened = []

    class Client:
        def search_vacancies_html(self, *a, **k):
            return "<html>"

        def get_vacancy_html(self, vacancy_id):
            opened.append(vacancy_id)
            return "<html>"

    jobs = HeadHunterBrowserSource(Client()).search(
        {
            "outputFileDirectory": tmp_path,
            "headhunter": {"positions": ["Python"]},
        }
    )
    # "1" уже есть у headhunter — страница не открывается; "2" записан
    # у другой площадки и для HH остаётся новой.
    assert opened == ["2"]
    assert [j.role for j in jobs] == ["r2"]


def test_hh_search_goes_deeper_when_first_pages_are_all_seen(
    tmp_path, monkeypatch
):
    """9.10: «сначала новые» — верх выдачи уже обработан, 2 страницы давали
    0 новых; бот должен дойти до страниц, где есть непросмотренные."""
    (tmp_path / "applied_log.json").write_text(
        json.dumps(
            {
                "applications": [
                    {"source": "headhunter", "external_id": str(i)}
                    for i in range(1, 5)  # страницы 0 и 1 целиком просмотрены
                ]
            }
        )
    )
    pages = {0: ["1", "2"], 1: ["3", "4"], 2: ["5", "6"]}
    asked = []

    class Client:
        def search_vacancies_html(self, query, remote_only, page=0, **k):
            asked.append(page)
            return page

        def get_vacancy_html(self, vacancy_id):
            return "<html>"

    monkeypatch.setattr(
        browser_source,
        "parse_search_results",
        lambda page: [
            SimpleNamespace(external_id=i, location="")
            for i in pages.get(page, [])
        ],
    )
    monkeypatch.setattr(
        browser_source,
        "hh_html_vacancy_to_job",
        lambda html, vid: SimpleNamespace(role=f"r{vid}", location=""),
    )
    monkeypatch.setattr(browser_source, "passes_blacklists", lambda j, p: True)

    jobs = HeadHunterBrowserSource(Client()).search(
        {
            "outputFileDirectory": tmp_path,
            "headhunter": {"positions": ["Python"]},
        }
    )

    assert asked == [0, 1, 2, 3]  # страница 3 пуста — выдача кончилась
    assert [j.role for j in jobs] == ["r5", "r6"]
