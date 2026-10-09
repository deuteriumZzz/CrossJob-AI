"""Habr Career: выдача читается страницами, пока те приносят новое."""

from types import SimpleNamespace

from src.job_sources.habr_career import source as habr


def test_walks_pages_until_nothing_new(tmp_path, monkeypatch):
    pages = {1: ["1", "2"], 2: ["3", "4"], 3: ["4"]}  # на 3-й только повтор
    asked = []

    class Client:
        def search_html(self, position, page=1, **k):
            asked.append(page)
            return page

        def get_vacancy_html(self, vacancy_id):
            return vacancy_id

    monkeypatch.setattr(
        habr, "parse_search_results", lambda p: pages.get(p, [])
    )
    monkeypatch.setattr(habr, "parse_search_dates", lambda p: {})
    monkeypatch.setattr(
        habr,
        "habr_vacancy_to_job",
        lambda html, vid: SimpleNamespace(role=f"r{vid}", location=""),
    )
    monkeypatch.setattr(habr, "passes_blacklists", lambda j, p: True)

    jobs = habr.HabrCareerSource(Client()).search(
        {
            "outputFileDirectory": tmp_path,
            "habr_career": {"positions": ["Python"]},
        }
    )

    assert [j.role for j in jobs] == ["r1", "r2", "r3", "r4"]
    assert asked == [1, 2, 3]
