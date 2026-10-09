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
