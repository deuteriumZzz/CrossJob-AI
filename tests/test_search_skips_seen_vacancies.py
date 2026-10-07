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
