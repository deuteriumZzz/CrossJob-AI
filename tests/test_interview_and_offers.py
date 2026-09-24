import tempfile
from pathlib import Path

import main
from src.job import Job
from src.job_sources.applied_log import AppliedLog
from src.job_sources.offers import compare_with_market
from src.webui import api
from tests.test_webui_api import client  # noqa: F401  (fixture)


def test_prepare_interview_generates_once_and_stores(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        data, out = Path(tmp) / "d", Path(tmp) / "o"
        data.mkdir(); out.mkdir()
        log = AppliedLog(out / "applied_log.json")
        log.record(Job(role="Dev", company="Acme", link="https://j/1",
                       source="headhunter", external_id="1"), "", "", "applied", 8, ["K8s"])
        calls, sent = [], []
        monkeypatch.setattr(main, "generate_interview_prep",
                            lambda *a: calls.append(a) or "1. Вопрос")
        monkeypatch.setattr(main, "notify", lambda p, t: sent.append(t))
        params = {"dataFolder": data, "outputFileDirectory": out}
        entry = log.find_by_source_and_external_id("headhunter", "1")

        assert main.prepare_interview(params, "key", entry) == "1. Вопрос"
        assert calls[0][4] == ["K8s"]
        assert sent and "Acme" in sent[0]
        stored = log.find_by_source_and_external_id("headhunter", "1")
        assert stored["interview_prep"] == "1. Вопрос"
        assert main.prepare_interview(params, "key", stored) == "1. Вопрос"
        assert len(calls) == 1
        assert main.prepare_interview(params, "", {**entry, "interview_prep": ""}) == ""


def test_compare_with_market():
    offers = [
        {"company": "A", "amount": 330000, "currency": "RUB"},
        {"company": "B", "amount": 5000, "currency": "USD"},
        {"company": "C", "amount": 100, "currency": "GBP"},
    ]
    market = [
        {"currency": "RUB", "median_max": 300000},
        {"currency": "USD", "median_max": 10000},
    ]
    result = compare_with_market(offers, market)
    assert [(o["company"], o["vs_market"]) for o in result] == [
        ("A", 10), ("B", -50), ("C", None),
    ]


def test_offers_api(client):  # noqa: F811
    offer = client.post("/api/offers", json={
        "company": "Acme", "amount": 300000, "currency": "RUB", "notes": "ДМС",
    }).json()
    assert offer["id"]
    assert [o["company"] for o in client.get("/api/offers").json()] == ["Acme"]
    client.delete(f"/api/offers/{offer['id']}")
    assert client.get("/api/offers").json() == []


def test_prep_endpoint(client, monkeypatch):  # noqa: F811
    ctx = api.get_ctx()
    ctx.applied_log.record(Job(role="Dev", company="Co", source="headhunter",
                               external_id="p1"), "", "", "applied", 8, [])
    monkeypatch.setattr(api, "_prepare_interview", lambda p, k, e: "справка")
    assert client.post("/api/applications/prep", json={
        "source": "headhunter", "external_id": "p1"}).json() == {"prep": "справка"}
    assert client.post("/api/applications/prep", json={
        "source": "headhunter", "external_id": "nope"}).status_code == 404


def test_build_ics_utc_and_escaping():
    from datetime import datetime, timedelta, timezone
    from src.job_sources.interview_calendar import build_ics

    start = datetime(2030, 1, 15, 15, 0, tzinfo=timezone(timedelta(hours=3)))
    ics = build_ics(start, "Интервью, Acme; Dev", "line1\nline2", "https://j/1", 45)
    assert "DTSTART:20300115T120000Z" in ics
    assert "DTEND:20300115T124500Z" in ics
    assert "SUMMARY:Интервью\\, Acme\; Dev" in ics
    assert "DESCRIPTION:line1\\nline2" in ics
    assert "TRIGGER:-PT30M" in ics
    assert ics.endswith("END:VCALENDAR\r\n")


def test_interview_invite_sent_only_with_exact_time(monkeypatch):
    from datetime import datetime, timezone

    docs = []
    monkeypatch.setattr(main, "send_document_from_secrets",
                        lambda p, name, content, caption: docs.append((name, content, caption)))
    job = {"company": "Acme", "title": "Dev", "link": "https://j/1"}
    monkeypatch.setattr(main, "extract_interview_time", lambda t, k: None)
    main._send_interview_invite({}, "key", job, "Созвонимся на неделе")
    assert docs == []
    monkeypatch.setattr(main, "extract_interview_time",
                        lambda t, k: datetime(2030, 1, 15, 12, 0, tzinfo=timezone.utc))
    main._send_interview_invite({}, "key", job, "Завтра в 15:00")
    [(name, content, caption)] = docs
    assert name == "interview.ics"
    assert b"DTSTART:20300115T120000Z" in content
    assert "Acme" in caption


def test_ics_and_trainer_endpoints(client, monkeypatch):  # noqa: F811
    ctx = api.get_ctx()
    ctx.applied_log.record(Job(role="Dev", company="Co", link="https://j/t1",
                               source="headhunter", external_id="t1"), "", "", "applied", 8, ["K8s"])
    r = client.get("/api/applications/ics", params={
        "source": "headhunter", "external_id": "t1", "start": "2030-01-15T15:00"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/calendar")
    assert "SUMMARY:Интервью — Co — Dev" in r.text
    assert client.get("/api/applications/ics", params={
        "source": "headhunter", "external_id": "t1", "start": "nope"}).status_code == 400

    calls = []
    monkeypatch.setattr(api, "generate_questions",
                        lambda title, company, gaps, key: calls.append(gaps) or ["Q1", "Q2"])
    body = {"source": "headhunter", "external_id": "t1"}
    assert client.post("/api/interview/questions", json=body).json() == {"questions": ["Q1", "Q2"]}
    assert client.post("/api/interview/questions", json=body).json() == {"questions": ["Q1", "Q2"]}
    assert calls == [["K8s"]]  # второй раз — из кэша

    monkeypatch.setattr(api, "evaluate_answer", lambda *a: "Хорошо. 8/10")
    res = client.post("/api/interview/feedback", json={**body, "question": "Q1", "answer": "Мой ответ"})
    assert res.json() == {"feedback": "Хорошо. 8/10"}
    assert client.post("/api/interview/feedback", json={**body, "question": "Q1", "answer": " "}).status_code == 400
