"""Himalayas: поиск через JSON-API, браузер — только если API упал."""

from src.job_sources.himalayas import source as himalayas_source


def _api_job(n):
    return himalayas_source.Job(
        role=f"Python {n}",
        company="Acme",
        location="",
        link=f"https://himalayas.app/companies/acme/jobs/python-{n}",
        description="text",
        source="himalayas",
        external_id=f"acme/python-{n}",
        apply_method="himalayas_manual",
    )


def test_pages_api_without_browser(monkeypatch):
    pages = {1: [_api_job(1), _api_job(2)], 2: [_api_job(3)]}
    monkeypatch.setattr(
        himalayas_source, "search_jobs_api", lambda q, p: pages.get(p, [])
    )
    monkeypatch.setattr(
        himalayas_source, "search_jobs", lambda *a: 1 / 0
    )
    prefs = {"himalayas": {"positions": ["Python Developer"]}}
    jobs = himalayas_source.HimalayasSource(None).search(prefs)
    assert [j.external_id for j in jobs] == [
        "acme/python-1", "acme/python-2", "acme/python-3"
    ]


def test_falls_back_to_browser_when_api_fails(monkeypatch):
    def boom(q, p):
        raise RuntimeError("down")

    monkeypatch.setattr(himalayas_source, "search_jobs_api", boom)
    monkeypatch.setattr(
        himalayas_source, "search_jobs", lambda *a: [_api_job(9)]
    )
    prefs = {"himalayas": {"positions": ["Python Developer"]}}
    jobs = himalayas_source.HimalayasSource(None).search(prefs)
    assert [j.external_id for j in jobs] == ["acme/python-9"]
