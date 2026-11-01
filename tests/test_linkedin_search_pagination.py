"""LinkedIn: выдача читается страницами (start=0,25,…), а не одной первой."""

from urllib.parse import parse_qs, urlparse

from src.job_sources.linkedin import search


class _Driver:
    def __init__(self, pages):
        self.pages, self.urls, self.page_source = pages, [], ""

    def get(self, url):
        self.urls.append(url)
        start = int(parse_qs(urlparse(url).query).get("start", ["0"])[0])
        self.page_source = self.pages.get(start // 25, "<html></html>")

    def execute_script(self, _js):
        return None


def _card(i):
    return (
        f'<div data-job-id="{i}"><a class="job-card-list__title--link" '
        f'aria-label="Job {i}"></a></div>'
    )


def test_walks_pages_until_one_brings_nothing_new(monkeypatch):
    monkeypatch.setattr(search.time, "sleep", lambda s: None)
    driver = _Driver(
        {
            0: "".join(_card(i) for i in (1, 2, 3)),
            1: "".join(_card(i) for i in (3, 4, 5)),  # 3 повторилась
            # страница 2 пустая — выдача кончилась
        }
    )

    jobs = search.search_easy_apply_jobs(driver, "python", "", {})

    assert [j.external_id for j in jobs] == ["1", "2", "3", "4", "5"]
    assert len(driver.urls) == 3
    assert "start=25" in driver.urls[1] and "start=50" in driver.urls[2]


def test_reads_new_search_results_cards(monkeypatch):
    """С 22.10 залогиненная выдача — /jobs/search-results/ без data-job-id."""
    monkeypatch.setattr(search.time, "sleep", lambda s: None)
    card = (
        '<div role="button" componentkey="job-card-component-ref-4484930138">'
        '<div componentkey="job-card-component-ref-4484930138">'
        '<p><span aria-hidden="true">Senior Backend Engineer</span></p>'
        "<p>Pashouses</p><p>Jakarta, Indonesia (Remote)</p></div></div>"
    )
    jobs = search.search_easy_apply_jobs(_Driver({0: card}), "python", "", {})

    assert [(j.external_id, j.role, j.company, j.location) for j in jobs] == [
        (
            "4484930138",
            "Senior Backend Engineer",
            "Pashouses",
            "Jakarta, Indonesia (Remote)",
        )
    ]
    assert jobs[0].link == "https://www.linkedin.com/jobs/view/4484930138/"


def test_remote_filter_is_applied_locally_not_via_f_wt(monkeypatch):
    """f_WT=2 новая выдача подменяет и режет до ~31 — фильтруем сами."""
    monkeypatch.setattr(search.time, "sleep", lambda s: None)

    def card(i, where):
        return (
            f'<div componentkey="job-card-component-ref-{i}">'
            f"<p>Python {i}</p><p>Acme</p><p>{where}</p></div>"
        )

    driver = _Driver(
        {0: card(1, "Jakarta (Remote)") + card(2, "Jakarta (On-site)")
         + card(3, "Worldwide")}
    )
    monkeypatch.setattr(
        search, "linkedin_search_params", lambda p: {"f_AL": "true", "f_WT": "2"}
    )
    jobs = search.search_easy_apply_jobs(driver, "python", "", {})
    assert [j.external_id for j in jobs] == ["1", "3"]
    assert "f_WT" not in driver.urls[0]
