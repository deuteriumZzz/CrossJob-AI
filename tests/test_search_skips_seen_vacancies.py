import json
from types import SimpleNamespace

import pytest

from src.job_sources.block_detection import PlatformBlockedError
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


def test_hh_search_limits_one_run_and_continues_from_next_page(
    tmp_path, monkeypatch
):
    asked = []

    class Client:
        def search_vacancies_html(self, query, remote_only, page=0, **kwargs):
            asked.append(page)
            return page

        def get_vacancy_html(self, vacancy_id):
            return "<html>"

    monkeypatch.setattr(
        browser_source,
        "parse_search_results",
        lambda page: [SimpleNamespace(external_id=str(page), location="")],
    )
    monkeypatch.setattr(
        browser_source,
        "hh_html_vacancy_to_job",
        lambda html, vid: SimpleNamespace(role=f"r{vid}", location=""),
    )
    monkeypatch.setattr(browser_source, "passes_blacklists", lambda j, p: True)
    source = HeadHunterBrowserSource(Client())
    prefs = {
        "outputFileDirectory": tmp_path,
        "headhunter": {"positions": ["Python"], "max_new_per_run": 100},
    }

    first = source.search(prefs)
    first_pages = asked[:]
    source.commit_scan_cursor()
    (tmp_path / "applied_log.json").write_text(
        json.dumps(
            {
                "applications": [
                    {"source": "headhunter", "external_id": str(page)}
                    for page in first_pages
                ]
            }
        )
    )
    asked.clear()
    second = source.search(prefs)

    assert len(first_pages) <= browser_source.PAGES_PER_RUN_PER_POSITION
    assert len(first) == len(first_pages)
    assert asked == [0, *range(len(first_pages), len(first_pages) * 2 - 1)]
    assert [j.role for j in second] == [f"r{i}" for i in asked[1:]]


def test_hh_search_new_vacancy_limit_rechecks_fresh_page_next_run(
    tmp_path, monkeypatch
):
    asked = []

    class Client:
        def search_vacancies_html(self, query, remote_only, page=0, **kwargs):
            asked.append(page)
            return page

        def get_vacancy_html(self, vacancy_id):
            return "<html>"

    monkeypatch.setattr(
        browser_source,
        "parse_search_results",
        lambda page: [
            SimpleNamespace(external_id=str(i), location="")
            for i in range(page * 10, page * 10 + 10)
        ],
    )
    monkeypatch.setattr(
        browser_source,
        "hh_html_vacancy_to_job",
        lambda html, vid: SimpleNamespace(role=f"r{vid}", location=""),
    )
    monkeypatch.setattr(browser_source, "passes_blacklists", lambda j, p: True)
    prefs = {
        "outputFileDirectory": tmp_path,
        "headhunter": {"positions": ["Python"], "max_new_per_run": 3},
    }

    first = HeadHunterBrowserSource(Client()).search(prefs)
    (tmp_path / "applied_log.json").write_text(
        json.dumps(
            {
                "applications": [
                    {"source": "headhunter", "external_id": str(i)}
                    for i in range(3)
                ]
            }
        )
    )
    second = HeadHunterBrowserSource(Client()).search(prefs)

    assert len(first) == len(second) == 3
    assert asked == [0, 0]
    assert [job.role for job in first] == ["r0", "r1", "r2"]
    assert [job.role for job in second] == ["r3", "r4", "r5"]


def test_hh_search_does_not_advance_cursor_after_captcha(
    tmp_path, monkeypatch
):
    asked = []

    class Client:
        def search_vacancies_html(self, query, remote_only, page=0, **kwargs):
            asked.append(page)
            if page == 1:
                raise PlatformBlockedError("captcha")
            return page

        def get_vacancy_html(self, vacancy_id):
            return "<html>"

    monkeypatch.setattr(
        browser_source,
        "parse_search_results",
        lambda page: [SimpleNamespace(external_id=str(page), location="")],
    )
    monkeypatch.setattr(
        browser_source,
        "hh_html_vacancy_to_job",
        lambda html, vid: SimpleNamespace(role=f"r{vid}", location=""),
    )
    monkeypatch.setattr(browser_source, "passes_blacklists", lambda j, p: True)
    prefs = {
        "outputFileDirectory": tmp_path,
        "headhunter": {"positions": ["Python"]},
    }

    with pytest.raises(PlatformBlockedError):
        HeadHunterBrowserSource(Client()).search(prefs)
    with pytest.raises(PlatformBlockedError):
        HeadHunterBrowserSource(Client()).search(prefs)

    assert asked == [0, 1, 0, 1]


def test_hh_scan_cursor_waits_until_found_jobs_are_processed(
    tmp_path, monkeypatch
):
    asked = []

    class Client:
        def search_vacancies_html(self, query, remote_only, page=0, **kwargs):
            asked.append(page)
            return page

        def get_vacancy_html(self, vacancy_id):
            return "<html>"

    monkeypatch.setattr(
        browser_source,
        "parse_search_results",
        lambda page: [SimpleNamespace(external_id=str(page), location="")],
    )
    monkeypatch.setattr(
        browser_source,
        "hh_html_vacancy_to_job",
        lambda html, vid: SimpleNamespace(role=f"r{vid}", location=""),
    )
    monkeypatch.setattr(browser_source, "passes_blacklists", lambda j, p: True)
    prefs = {
        "outputFileDirectory": tmp_path,
        "headhunter": {"positions": ["Python"], "max_new_per_run": 20},
    }

    first_source = HeadHunterBrowserSource(Client())
    first_source.search(prefs)
    assert not (tmp_path / ".hh_scan_cursor.json").exists()

    asked.clear()
    HeadHunterBrowserSource(Client()).search(prefs)
    assert asked == [0, 1, 2, 3, 4, 5]

    first_source.commit_scan_cursor()
    assert json.loads((tmp_path / ".hh_scan_cursor.json").read_text()) == {
        "Python": [6, 0]
    }


def test_hh_search_stops_when_browser_connection_dies(tmp_path, monkeypatch):
    driver = object()

    class Client:
        _driver = driver

        def search_vacancies_html(self, query, remote_only, page=0, **kwargs):
            return page

        def get_vacancy_html(self, vacancy_id):
            raise ConnectionError("ChromeDriver connection refused")

    monkeypatch.setattr(
        browser_source,
        "parse_search_results",
        lambda page: [SimpleNamespace(external_id="1", location="")],
    )
    monkeypatch.setattr(
        browser_source, "is_driver_dead", lambda d: d is driver
    )

    with pytest.raises(ConnectionError, match="ChromeDriver"):
        HeadHunterBrowserSource(Client()).search(
            {
                "outputFileDirectory": tmp_path,
                "headhunter": {"positions": ["Python"]},
            }
        )
    assert not (tmp_path / ".hh_scan_cursor.json").exists()


def test_hh_detail_failure_does_not_advance_deep_scan_cursor(
    tmp_path, monkeypatch
):
    cursor_path = tmp_path / ".hh_scan_cursor.json"
    cursor_path.write_text(json.dumps({"Python": [2, 0]}))
    asked = []

    class Client:
        def search_vacancies_html(self, query, remote_only, page=0, **kwargs):
            asked.append(page)
            return page

        def get_vacancy_html(self, vacancy_id):
            if vacancy_id == "2":
                raise TimeoutError("temporary page failure")
            return "<html>"

    monkeypatch.setattr(
        browser_source,
        "parse_search_results",
        lambda page: [SimpleNamespace(external_id=str(page), location="")],
    )
    monkeypatch.setattr(
        browser_source,
        "hh_html_vacancy_to_job",
        lambda html, vid: SimpleNamespace(role=f"r{vid}", location=""),
    )
    monkeypatch.setattr(browser_source, "passes_blacklists", lambda j, p: True)
    monkeypatch.setattr(browser_source, "is_driver_dead", lambda d: False)

    source = HeadHunterBrowserSource(Client())
    source.search(
        {
            "outputFileDirectory": tmp_path,
            "headhunter": {"positions": ["Python"]},
        }
    )
    source.commit_scan_cursor()

    assert asked == [0, 2, 3, 4, 5, 6]
    assert json.loads(cursor_path.read_text()) == {"Python": [2, 0]}
