"""hirify.me как сборщик: разбор списка и страницы, фильтры, источник."""

import json

from src.job_sources.hirify.mapping import (
    channels_from_links,
    contacts_block,
    parse_job,
    parse_list,
)
from src.job_sources.hirify.source import HirifySource, matches_filters

JOB_HTML = (
    '<script type="application/ld+json">'
    + json.dumps(
        {
            "@type": "JobPosting",
            "title": "Python Developer",
            "description": "<b>ООО Ромашка</b><br>Пишите на hr@romashka.io",
            "datePosted": "2026-10-07T10:00:00Z",
            "hiringOrganization": {"name": "Ромашка"},
            "employmentType": ["FULL_TIME"],
            "jobLocationType": "TELECOMMUTE",
            "applicantLocationRequirements": [{"name": "Russia"}],
            "url": "https://hirify.me/jobs/7-python-dev",
        }
    )
    + "</script>"
)


def test_parse_list_unique_ids_in_order():
    html = (
        '<a href="/jobs/5-a">x</a><a href="/jobs/5-a">x</a>'
        '<a href="/jobs/6-b?x=1">y</a>'
    )
    assert parse_list(html) == [
        {"id": "5", "slug": "a"},
        {"id": "6", "slug": "b"},
    ]


def test_parse_job_reads_markup():
    job, meta = parse_job(JOB_HTML, "7")
    assert (job.role, job.company, job.source) == (
        "Python Developer",
        "Ромашка",
        "hirify",
    )
    assert "hr@romashka.io" in job.description and "<" not in job.description
    assert meta == {
        "posted_at": "2026-10-07T10:00:00Z",
        "employment": ["FULL_TIME"],
        "remote": True,
    }
    assert parse_job("<html></html>", "1") is None


def test_channels_from_links_and_contacts_block():
    hrefs = [
        "https://t.me/job_python/8014",
        "https://t.me/job_python/8014",
        "https://t.me/hirify_support_bot",
        "https://t.me/c/12345/9",
        "https://t.me/other_jobs",
        "https://hirify.me/jobs/1",
    ]
    assert channels_from_links(hrefs) == ["job_python", "other_jobs"]
    page = (
        "Описание ... Ссылки для отклика: email: hr@alfa.ru "
        "Не входите под своими аккаунтами ... @hirify_support"
    )
    assert contacts_block(page) == "email: hr@alfa.ru"
    assert contacts_block("нет окна") == ""


def test_matches_filters_by_format_employment_and_period():
    remote = {
        "posted_at": "2020-01-01T00:00:00Z",
        "employment": ["FULL_TIME"],
        "remote": True,
    }
    assert matches_filters(remote, {})
    assert not matches_filters(remote, {"onsite": True})
    assert matches_filters(remote, {"remote": True})
    assert not matches_filters(remote, {"employment_types": ["part"]})
    assert not matches_filters(remote, {"posted_within_days": 7})
    office = {**remote, "remote": False}
    assert not matches_filters(office, {"remote": True})
    assert matches_filters(office, {"onsite": True})


class _FakeClient:
    def list_html(self, query, page=1):
        return '<a href="/jobs/7-python-dev">x</a>' if page == 1 else ""

    def job_html(self, job_id, slug):
        return JOB_HTML


def test_source_returns_filtered_jobs():
    prefs = {"positions": ["python"], "remote": True}
    jobs = HirifySource(_FakeClient()).search(prefs)
    assert [j.external_id for j in jobs] == ["7"]
    assert jobs[0].link == "https://hirify.me/jobs/7-python-dev"
    assert (
        HirifySource(_FakeClient()).search(
            {"positions": ["python"], "onsite": True}
        )
        == []
    )
