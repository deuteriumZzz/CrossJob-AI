"""hirify.me как сборщик: разбор списка и страницы, фильтры, источник."""

import json
from types import SimpleNamespace

import pytest

from src.job_sources.hirify.mapping import (
    channels_from_links,
    contacts_block,
    hirify_apply_contacts,
    parse_job,
    parse_list,
)
from src.job_sources.hirify.source import HirifySource, matches_filters
from src.job_sources.hirify.workspace import (
    backfill_hirify_vacancies,
    refresh_hirify_post_contacts,
    save_hirify_vacancy,
)
from src.job_sources.telegram.watcher import (
    get_watch_post,
    list_watch_posts,
    update_watch_post,
)

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


def test_contacts_block_reads_english_dialog():
    page = (
        "Job description. Links to apply: Telegram @hiring_team, "
        "email hr@example.org. Be careful: never send passwords."
    )
    assert contacts_block(page) == (
        "Telegram @hiring_team, email hr@example.org."
    )


def test_hirify_client_clicks_english_show_contacts(monkeypatch, tmp_path):
    from src.job_sources.hirify import client as hirify_client

    class Button:
        text = "Show contacts"
        tag_name = "button"

        def is_displayed(self):
            return True

        def get_attribute(self, name):
            return None

    class Driver:
        clicked = False

        def get(self, url):
            pass

        def find_elements(self, by, selector):
            return [Button()]

        def execute_script(self, script, *args):
            if args:
                self.clicked = True
            if script.startswith(
                "return [...document.querySelectorAll('a[href]')]"
            ):
                return []
            return None

    driver = Driver()
    monkeypatch.setattr(hirify_client.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(hirify_client, "raise_if_page_blocked", lambda d: None)
    monkeypatch.setattr(
        hirify_client,
        "visible_text",
        lambda d: (
            "Links to apply: hr@example.org and @hiring_team. Be careful"
            if d.clicked
            else "Job description"
        ),
    )
    with hirify_client.HirifyClient(tmp_path) as client:
        info = client._read_contacts(driver, "7", "python-dev")
    assert driver.clicked
    assert {c["value"] for c in hirify_apply_contacts(info["text"])} == {
        "hr@example.org",
        "hiring_team",
    }


def test_hirify_apply_contacts_reads_explicit_username_and_email():
    contacts = hirify_apply_contacts(
        "Канал: @jobs_it\n"
        "Связь: @nextbit_hr или hr@romashka.io. "
        "Канал: @hirify_support_bot"
    )
    assert {c["value"] for c in contacts} == {
        "nextbit_hr",
        "hr@romashka.io",
    }


def test_hirify_vacancy_is_saved_for_workspace_without_sending(tmp_path):
    job, _ = parse_job(JOB_HTML, "7")
    contact = {"kind": "telegram", "value": "nextbit_hr"}
    post_id = save_hirify_vacancy(tmp_path, job, [contact])
    post = get_watch_post(tmp_path, post_id)
    assert post["source"] == "hirify"
    assert post["channel"] == "Hirify"
    assert post["title"] == job.role
    assert post["text"] == job.description
    assert post["link"] == job.link
    assert contact in post["contacts"]
    assert not list(tmp_path.glob("*pending*"))

    update_watch_post(tmp_path, post_id, status="sent")
    save_hirify_vacancy(tmp_path, job, [contact])
    assert get_watch_post(tmp_path, post_id)["status"] == "sent"


def test_refresh_existing_hirify_post_saves_modal_contacts(tmp_path):
    from src.job_sources.contact_book import ContactBook

    job, _ = parse_job(JOB_HTML, "7")
    post_id = save_hirify_vacancy(tmp_path, job, [])
    update_watch_post(tmp_path, post_id, status="later", send_after="tomorrow")

    class Client:
        def show_contacts(self, job_id, slug):
            assert (job_id, slug) == ("7", "python-dev")
            return {
                "text": "Links to apply: hr@example.org and @hiring_team.",
                "channels": ["source_jobs"],
                "needs_login": False,
            }

    result = refresh_hirify_post_contacts(tmp_path, post_id, Client())
    assert result["channels"] == ["source_jobs"]
    assert {c["value"] for c in result["contacts"]} == {
        "hr@example.org",
        "hiring_team",
    }
    saved = get_watch_post(tmp_path, post_id)
    assert saved["status"] == "later"
    assert saved["send_after"] == "tomorrow"
    assert {c["value"] for c in saved["contacts"]} == {
        "hr@example.org",
        "hiring_team",
    }
    card = next(iter(ContactBook(tmp_path).all().values()))
    assert {c["value"] for c in card["contacts"]} == {
        "hr@example.org",
        "hiring_team",
    }
    assert all(c["source_url"] == job.link for c in card["contacts"])


def test_refresh_hirify_contacts_rejects_login_and_wrong_source(tmp_path):
    import pytest

    job, _ = parse_job(JOB_HTML, "7")
    post_id = save_hirify_vacancy(tmp_path, job, [])

    class Client:
        def show_contacts(self, job_id, slug):
            return {"text": "", "channels": [], "needs_login": True}

    with pytest.raises(ValueError, match="Войдите"):
        refresh_hirify_post_contacts(tmp_path, post_id, Client())
    from src.job_sources.contact_book import ContactBook

    assert ContactBook(tmp_path).all() == {}
    update_watch_post(tmp_path, post_id, source="telegram")
    with pytest.raises(ValueError, match="Hirify"):
        refresh_hirify_post_contacts(tmp_path, post_id, Client())


def test_hirify_contact_refresh_api_uses_saved_browser_profile(
    monkeypatch, tmp_path
):
    from fastapi import HTTPException

    from src.job_sources.hirify import client as hirify_client
    from src.job_sources.talanto import channels as channel_router
    from src.webui.api import refresh_hirify_contacts

    job, _ = parse_job(JOB_HTML, "7")
    post_id = save_hirify_vacancy(tmp_path, job, [])

    class Client:
        def __init__(self, profile_dir):
            assert profile_dir == tmp_path / ".chrome_profile_hirify"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def show_contacts(self, job_id, slug):
            return {
                "text": "Links to apply: hr@example.org",
                "channels": ["source_jobs"],
                "needs_login": False,
            }

    monkeypatch.setattr(hirify_client, "HirifyClient", Client)
    routed = []
    monkeypatch.setattr(
        channel_router,
        "route_telegram_handles",
        lambda config, handles: routed.extend(handles) or [],
    )
    context = SimpleNamespace(output_folder=tmp_path, config={})
    assert (
        refresh_hirify_contacts(post_id, ctx=context)["contacts"][0]["value"]
        == "hr@example.org"
    )
    assert routed == ["source_jobs"]
    with pytest.raises(HTTPException) as exc:
        refresh_hirify_contacts("missing", ctx=context)
    assert exc.value.status_code == 409


def test_hirify_login_action_opens_application_browser(monkeypatch, tmp_path):
    from src.utils import chrome_utils, shared_browser
    from src.webui.api import open_hirify_login

    opened = []

    class Browser:
        def get(self, url):
            opened.append(url)

    monkeypatch.setattr(chrome_utils, "init_browser", lambda path: Browser())
    monkeypatch.setattr(chrome_utils, "is_driver_dead", lambda driver: False)
    monkeypatch.setattr(
        shared_browser,
        "reveal_shared_browser",
        lambda: opened.append("visible"),
    )
    context = SimpleNamespace(output_folder=tmp_path, hirify_login_driver=None)
    open_hirify_login(ctx=context)
    assert opened == ["https://hirify.me/", "visible"]
    assert context.hirify_login_driver is not None


def test_existing_hirify_vacancy_backfills_only_its_own_contacts(tmp_path):
    from src.job_sources.contact_book import ContactBook

    first_url = "https://hirify.me/jobs/7-python-dev"
    second_url = "https://hirify.me/jobs/8-data-dev"
    ContactBook(tmp_path).add(
        "Ромашка",
        [
            {
                "kind": "telegram",
                "value": "first_hr",
                "source": "Hirify: контакты",
                "source_url": first_url,
            },
            {
                "kind": "email",
                "value": "second@romashka.io",
                "source": "Hirify: контакты",
                "source_url": second_url,
            },
        ],
        vacancy={
            "title": "Python Developer",
            "link": first_url,
            "source": "hirify",
            "text": "Связь в модальном окне",
        },
    )

    assert backfill_hirify_vacancies(tmp_path) == 1
    assert backfill_hirify_vacancies(tmp_path) == 0
    posts = list_watch_posts(tmp_path)
    assert len(posts) == 1
    post = next(iter(posts.values()))
    assert post["source"] == "hirify"
    assert [(c["kind"], c["value"]) for c in post["contacts"]] == [
        ("telegram", "first_hr")
    ]
    assert post["contacts"][0]["source"] == "Hirify: контакты"


def test_search_hirify_bridges_vacancy_and_keeps_channel_routing(
    tmp_path, monkeypatch
):
    import main

    job, _ = parse_job(JOB_HTML, "7")
    job.link = "https://hirify.me/jobs/7-python-dev"
    job.description += "\nСвязь: @nextbit_hr"

    class FakeClient:
        def __init__(self, profile_dir):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def show_contacts(self, job_id, slug):
            return {
                "text": "Пишите на hr@romashka.io",
                "channels": ["jobs_it"],
                "needs_login": False,
            }

    monkeypatch.setattr(main, "HirifyClient", FakeClient)
    monkeypatch.setattr(
        main,
        "HirifySource",
        lambda client: SimpleNamespace(search=lambda p: [job]),
    )
    monkeypatch.setattr(
        main,
        "score_job_fit",
        lambda *args: SimpleNamespace(score=90, gaps=[]),
    )
    monkeypatch.setattr(main, "classify_fit", lambda *args: "good")
    monkeypatch.setattr(main, "_record_last_run_summary", lambda *args: None)
    monkeypatch.setattr(main, "notify_routine", lambda *args, **kwargs: None)
    routed = []
    monkeypatch.setattr(
        main,
        "route_telegram_handles",
        lambda params, handles: routed.extend(handles) or ["jobs_it"],
    )
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / main.RESUME_PDF).write_bytes(b"pdf")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    main.search_hirify(
        {"dataFolder": data_dir, "outputFileDirectory": output_dir},
        "unused",
    )

    from src.job_sources.telegram.watcher import list_watch_posts

    posts = list_watch_posts(output_dir)
    assert len(posts) == 1
    post = next(iter(posts.values()))
    assert post["source"] == "hirify"
    assert {c["value"] for c in post["contacts"]} >= {
        "nextbit_hr",
        "hr@romashka.io",
    }
    assert "jobs_it" in routed
    assert not list(output_dir.glob("*pending*"))


def test_search_hirify_rechecks_saved_vacancy_missing_contacts(
    tmp_path, monkeypatch
):
    import main

    job, _ = parse_job(JOB_HTML, "7")
    job.description = "Адреса в описании нет"
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    post_id = save_hirify_vacancy(output_dir, job, [])

    class FakeClient:
        def __init__(self, profile_dir):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def show_contacts(self, job_id, slug):
            return {
                "text": "Links to apply: hr@example.org",
                "channels": ["source_jobs"],
                "needs_login": False,
            }

    monkeypatch.setattr(main, "HirifyClient", FakeClient)
    monkeypatch.setattr(
        main,
        "HirifySource",
        lambda client: SimpleNamespace(search=lambda p: []),
    )
    monkeypatch.setattr(main, "_record_last_run_summary", lambda *a: None)
    monkeypatch.setattr(main, "notify_routine", lambda *a, **kw: None)
    routed = []
    monkeypatch.setattr(
        main,
        "route_telegram_handles",
        lambda params, handles: routed.extend(handles) or [],
    )
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / main.RESUME_PDF).write_bytes(b"pdf")
    main.search_hirify(
        {"dataFolder": data_dir, "outputFileDirectory": output_dir},
        "unused",
    )
    assert [
        c["value"] for c in get_watch_post(output_dir, post_id)["contacts"]
    ] == ["hr@example.org"]
    assert "source_jobs" in routed


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


def test_office_text_overrides_telecommute_label():
    """9.10: Совкомбанк — «Новосибирск, офисный формат», а метка Hirify
    TELECOMMUTE; для поиска «только удалёнка» вакансия не подходит."""
    import json as _json

    from src.job_sources.hirify.mapping import parse_job

    def page(desc):
        data = {
            "@type": "JobPosting",
            "title": "Python",
            "jobLocationType": "TELECOMMUTE",
            "description": desc,
            "hiringOrganization": {"name": "Bank"},
        }
        return (
            f'<script type="application/ld+json">{_json.dumps(data)}</script>'
        )

    _, office = parse_job(page("Локация: Новосибирск, офисный формат"), "1")
    _, remote = parse_job(page("Локация: удалённо, гибкий график"), "2")
    assert office["remote"] is False
    assert remote["remote"] is True
