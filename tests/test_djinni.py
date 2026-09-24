import json
from pathlib import Path

import httpx

import main
from src.job_sources.djinni import search as dj


def _page(ids, company="Acme"):
    items = [{
        "@type": "JobPosting", "title": f"Python Dev {i}", "url": f"https://djinni.co/jobs/{i}-python-dev/",
        "identifier": i, "hiringOrganization": {"@type": "Organization", "name": company} if i % 2 else company,
        "description": "Build APIs &amp; services", "jobLocationType": "TELECOMMUTE",
        "applicantLocationRequirements": [{"address": {"addressCountry": "POL"}}],
    } for i in ids]
    # В настоящей странице есть reCAPTCHA формы входа — это не блокировка.
    return f'<script src="recaptcha"></script><script type="application/ld+json">{json.dumps(items)}</script>'


def test_parse_jobs_from_json_ld():
    jobs = dj.parse_jobs(_page([1, 2]))
    assert [(j.role, j.company, j.location, j.external_id, j.source) for j in jobs] == [
        ("Python Dev 1", "Acme", "Remote, POL", "1", "djinni"),
        ("Python Dev 2", "Acme", "Remote, POL", "2", "djinni"),  # компания строкой
    ]
    assert jobs[0].description == "Build APIs & services"


def test_search_params():
    assert dj.search_params("Python разработчик") == {"primary_keyword": "Python"}
    assert dj.search_params("Backend developer", 2) == {"all_keywords": "Backend developer", "search_type": "full-text", "page": 2}
    assert dj.search_params("Разработчик") == {}


def test_search_pages_dedupes_and_ignores_login_captcha(monkeypatch):
    monkeypatch.setattr(dj.time, "sleep", lambda s: None)
    pages = {1: _page(range(1, 16)), 2: _page(range(10, 20))}  # вторая неполная, с повторами

    def handler(request):
        page = int(request.url.params.get("page", 1))
        return httpx.Response(200, text=pages.get(page, _page([])))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    jobs = dj.search({"positions": ["Python developer"]}, client)
    assert len(jobs) == 19 and len({j.external_id for j in jobs}) == 19


def test_search_only_mode_records_dry_run_without_browser(tmp_path, monkeypatch):
    (tmp_path / "resume.pdf").write_bytes(b"%PDF")
    out = tmp_path / "output"
    out.mkdir()
    job = dj.parse_jobs(_page([7]))[0]
    monkeypatch.setattr(main, "search_djinni_jobs", lambda p: [job])
    monkeypatch.setattr(main, "score_job_fit", lambda *a, **k: type("F", (), {"score": 8, "gaps": []})())
    monkeypatch.setattr(main, "generate_cover_letter_for_job", lambda *a, **k: "Hello")
    monkeypatch.setattr(main, "DjinniSession", lambda *a: (_ for _ in ()).throw(AssertionError("браузер не нужен")))
    main.search_and_apply_djinni({"dataFolder": tmp_path, "outputFileDirectory": out, "djinni": {"auto_apply": False}}, "key")
    entry = json.loads((out / "applied_log.json").read_text())["applications"][0]
    assert entry["source"] == "djinni" and entry["status"] == "dry_run" and entry["cover_letter"] == "Hello"


def test_country_and_experience_prefilter():
    item = lambda i, countries, months: {  # noqa: E731
        "@type": "JobPosting", "title": f"Job {i}", "url": f"https://djinni.co/jobs/{i}/", "identifier": i,
        "hiringOrganization": "Acme", "applicantLocationRequirements": countries,
        "experienceRequirements": {"monthsOfExperience": months},
    }
    html = "<script type=\"application/ld+json\">" + json.dumps([
        item(1, {"@type": "Country", "address": {"addressCountry": "POL"}}, 12),  # одним объектом
        item(2, [], 60),                                                          # стаж 5 лет
        item(3, [{"address": {"addressCountry": "IDN"}}], 24),
        item(4, [], 12),
    ]) + "</script>"
    assert [j.external_id for j in dj.parse_jobs(html, "IDN", 1.5 * 12 + 12)] == ["3", "4"]
    assert len(dj.parse_jobs(html)) == 4


def test_unmet_requirements_reads_djinni_reasons(monkeypatch):
    from src.job_sources.djinni import apply as da

    page = ("Apply\nYour profile does not meet some of the requirements specified by the company\n"
            "Only from 7 years of experience\nYour experience: 1.5 years of experience\n"
            "English B2 - Upper Intermediate\nYour level: B1 - Intermediate\nupdate your profile\nFooter")
    monkeypatch.setattr(da, "visible_text", lambda d: page)
    monkeypatch.setattr(da.time, "sleep", lambda s: None)
    driver = type("D", (), {"get": lambda self, url: None})()
    assert da.unmet_requirements(driver, "u") == [
        "Only from 7 years of experience", "Your experience: 1.5 years of experience",
        "English B2 - Upper Intermediate", "Your level: B1 - Intermediate",
    ]
    monkeypatch.setattr(da, "visible_text", lambda d: "Job text\nApply")
    assert da.unmet_requirements(driver, "u") == []


def test_bump_schedule(tmp_path):
    assert main._djinni_bump_due(tmp_path)  # ни разу не поднимали
    main._djinni_bump_done(tmp_path, "not_yet:3")
    assert not main._djinni_bump_due(tmp_path)
    state = json.loads((tmp_path / main.DJINNI_BUMP_FILE).read_text())
    assert state["last_result"] == "not_yet:3"


def test_bump_profile_waits_when_djinni_says_so(monkeypatch):
    from src.job_sources.djinni import apply as da

    monkeypatch.setattr(da, "get_with_retry", lambda d, url: None)
    monkeypatch.setattr(da.time, "sleep", lambda s: None)
    monkeypatch.setattr(da, "visible_text", lambda d: "Last bumped 25 September · you can bump again in 7d\\nBump My Profile")
    clicked = []
    driver = type("D", (), {"find_elements": lambda self, *a: clicked.append(1) or []})()
    assert da.bump_profile(driver) == "not_yet:7" and not clicked  # кнопку даже не ищет
