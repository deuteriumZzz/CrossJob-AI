import tempfile
from pathlib import Path

import main
from src.direct import ats
from src.direct.boards import parse_hn_comment, parse_wwr_rss
from src.direct.contacts import extract_emails
from src.direct.email_channel import build_message
from src.direct.source import matches_positions
from src.job import Job
from src.job_sources.applied_log import AppliedLog
from src.job_sources.hr_replies import DraftStore
from src.webui import api
from tests.test_webui_api import client  # noqa: F401  (fixture)


def test_find_ats_in_html():
    assert ats.find_ats_in_html('<a href="https://jobs.lever.co/acme/123">') == ("lever", "acme")
    assert ats.find_ats_in_html('src="https://boards.greenhouse.io/embed/job_board?for=acme"') == ("greenhouse", "acme")
    assert ats.find_ats_in_html('https://job-boards.greenhouse.io/gitlab/jobs/1') == ("greenhouse", "gitlab")
    assert ats.find_ats_in_html("https://jobs.ashbyhq.com/Linear") == ("ashby", "Linear")
    assert ats.find_ats_in_html("<html>nothing</html>") is None


def test_extract_emails_obfuscated_and_filtered():
    text = (
        "Email jobs [at] acme [dot] io or cto@acme.io. "
        "Privacy: privacy@acme.io, noreply@acme.io, see you@example.com."
    )
    assert extract_emails(text) == ["jobs@acme.io", "cto@acme.io"]


def test_parse_wwr_rss():
    xml = """<rss><channel><item>
      <title>Acme: Senior Python Engineer</title>
      <region>Anywhere in the World</region>
      <link>https://weworkremotely.com/remote-jobs/acme-senior-python</link>
      <description>&lt;p&gt;Python &amp;amp; Django&lt;/p&gt;</description>
    </item></channel></rss>"""
    [job] = parse_wwr_rss(xml)
    assert (job.company, job.role, job.location) == (
        "Acme", "Senior Python Engineer", "Anywhere in the World",
    )
    assert job.external_id == "wwr-acme-senior-python"
    assert "Python & Django" in job.description


def test_parse_hn_comment():
    job = parse_hn_comment({
        "id": 42,
        "text": "Acme | Backend Engineer (Python) | Remote (EU) | Full-time<p>Write to jobs@acme.io",
    })
    assert (job.company, job.role, job.location) == (
        "Acme", "Backend Engineer (Python)", "Remote (EU) | Full-time",
    )
    assert job.link.endswith("id=42")
    assert parse_hn_comment({"id": 1, "text": "just chatting"}) is None


def test_matches_positions():
    positions = ["Python разработчик", "Backend developer"]
    assert matches_positions(Job(role="Senior Python Developer"), positions)
    assert matches_positions(Job(role="Backend Engineer"), positions)
    assert not matches_positions(Job(role="Frontend Developer"), positions)
    assert matches_positions(Job(role="Anything"), [])


def test_build_message_threads_follow_up():
    msg = build_message("me@x.io", "hr@acme.io", "Re: Dev", "Hi", in_reply_to="<abc@x>")
    assert msg["In-Reply-To"] == "<abc@x>"
    assert msg["References"] == "<abc@x>"
    assert msg["Message-ID"]


def test_send_email_draft_records_outreach_and_respects_limit(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        data, out = Path(tmp) / "data", Path(tmp) / "out"
        data.mkdir(); out.mkdir()
        secrets = data / "secrets.yaml"
        secrets.write_text(
            "email:\n  address: me@x.io\n  app_password: p\n", encoding="utf-8"
        )
        (data / main.RESUME_PDF).write_bytes(b"%PDF")
        params = {"dataFolder": data, "outputFileDirectory": out,
                  "secretsFile": secrets, "direct": {"email_daily_limit": 1}}
        log = AppliedLog(out / "applied_log.json")
        for n in ("1", "2"):
            log.record(Job(role="Dev", company=f"Co{n}", link=f"https://j/{n}",
                           source="direct", external_id=n), "", "", "dry_run", 8, [])
        sent = []
        monkeypatch.setattr(main, "send_email", lambda creds, m: sent.append(m) or "<id1>")
        drafts = DraftStore(out / main.HR_DRAFTS_FILE)
        code = drafts.add("hr@co1.io", "Letter", "email", "https://j/1",
                          channel="email", subject="Dev")
        assert main.send_hr_draft(params, code) == "Отправлено hr@co1.io."
        entry = log.find_by_source_and_external_id("direct", "1")
        assert entry["outreach_email"] == "hr@co1.io"
        assert entry["outreach_message_id"] == "<id1>"
        assert sent[0].get_payload()[1].get_filename() == main.RESUME_PDF

        code2 = drafts.add("hr@co2.io", "Letter", "email", "https://j/2",
                           channel="email", subject="Dev")
        assert "лимит" in main.send_hr_draft(params, code2)
        assert len(sent) == 1


def test_companies_api(client, monkeypatch):  # noqa: F811
    monkeypatch.setattr(api, "discover_ats", lambda site: ("lever", "acme"))
    monkeypatch.setattr(api, "fetch_jobs", lambda c: [Job(role="Dev")] * 3)
    body = client.post("/api/direct/companies", json={"website": "acme.io", "name": "Acme"}).json()
    assert body == {"name": "Acme", "website": "acme.io", "ats": "lever", "slug": "acme", "jobs": 3}
    assert [c["slug"] for c in client.get("/api/direct/companies").json()] == ["acme"]
    client.delete("/api/direct/companies/acme")
    assert client.get("/api/direct/companies").json() == []
    monkeypatch.setattr(api, "discover_ats", lambda site: None)
    assert client.post("/api/direct/companies", json={"website": "x.io"}).status_code == 404


def test_prefill_direct_application_passes_profile_and_letter(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        data, out = Path(tmp) / "data", Path(tmp) / "out"
        data.mkdir(); out.mkdir()
        (data / main.PLAIN_TEXT_RESUME_YAML).write_text(
            "personal_information:\n  name: Ann\n  email: ann@x.io\n", encoding="utf-8"
        )
        (data / main.RESUME_PDF).write_bytes(b"%PDF")
        AppliedLog(out / "applied_log.json").record(
            Job(role="Dev", company="Co", link="https://job-boards.greenhouse.io/co/jobs/1",
                source="direct", external_id="gh-co-1"),
            "My letter", "", "dry_run", 8, [],
        )
        calls = []
        monkeypatch.setattr(main, "init_browser", lambda profile: "driver")
        monkeypatch.setattr(main, "prefill_application",
                            lambda *a: calls.append(a) or ["first_name"])
        params = {"dataFolder": data, "outputFileDirectory": out}
        assert main.prefill_direct_application(params, "direct", "gh-co-1") == ["first_name"]
        driver, link, person, resume, letter = calls[0]
        assert link.endswith("/jobs/1")
        assert person == {"name": "Ann", "email": "ann@x.io"}
        assert resume.name == main.RESUME_PDF
        assert letter == "My letter"
        main._PREFILL_BROWSERS.clear()
