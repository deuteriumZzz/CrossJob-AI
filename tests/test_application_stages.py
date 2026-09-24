import tempfile
from datetime import datetime, timezone
from pathlib import Path

from src.job import Job
from src.job_sources.applied_log import AppliedLog, effective_stage
from src.job_sources.telegram_conversations import TelegramConversations
from src.webui import api
from tests.test_webui_api import client  # noqa: F401  (fixture)


def _job(n: str, source: str = "headhunter") -> Job:
    return Job(
        role=f"Dev {n}",
        company=f"Co {n}",
        link=f"https://example.com/{n}",
        source=source,
        external_id=n,
    )


def test_effective_stage_from_hh_state_and_manual_override():
    assert effective_stage({}) is None
    assert effective_stage({"last_known_state": "Не просмотрен"}) is None
    assert effective_stage({"last_known_state": "Просмотрен"}) is None
    assert effective_stage({"last_known_state": "Отказ"}) == "rejected"
    assert (
        effective_stage({"last_known_state": "Приглашение"}) == "interview"
    )
    assert effective_stage({"last_known_state": "Есть ответ"}) == "replied"
    assert (
        effective_stage({"last_known_state": "Отказ", "stage": "offer"})
        == "offer"
    )


def test_set_stage_and_funnel():
    with tempfile.TemporaryDirectory() as tmp:
        log = AppliedLog(Path(tmp) / "applied_log.json")
        for n in ("1", "2", "3"):
            log.record(_job(n), "", "", "applied", 8, [])
        log.record(_job("4"), "", "", "dry_run", 8, [])

        assert log.set_stage("headhunter", "1", "interview") is True
        assert log.set_stage("headhunter", "2", "rejected") is True
        assert log.set_stage("headhunter", "404", "offer") is False

        funnel = log.funnel()
        assert funnel["applied"] == 3
        assert funnel["interview"] == 1
        assert funnel["rejected"] == 1
        assert funnel["offer"] == 0

        log.set_stage("headhunter", "1", None)
        entry = log.find_by_source_and_external_id("headhunter", "1")
        assert "stage" not in entry


def test_inbox_merges_hh_replies_and_telegram_dialogs(client):  # noqa: F811
    ctx = api.get_ctx()
    ctx.applied_log.record(_job("1"), "", "", "applied", 8, [])
    ctx.applied_log.update_reply_state("headhunter", "1", "Приглашение")
    tg_job = _job("tg", source="telegram")
    ctx.applied_log.record(tg_job, "", "", "applied", 7, [])

    conversations = TelegramConversations(
        ctx.output_folder / "telegram_conversations.json"
    )
    conversations.record_outbound("hr_anna", "Здравствуйте!", tg_job.link)
    conversations.record_inbound(
        "hr_anna", "Какие ожидания по зарплате?", 5,
        datetime(2030, 1, 1, tzinfo=timezone.utc),
    )
    # Диалог без ответа HR во "Входящие" не попадает.
    conversations.record_outbound("hr_silent", "Добрый день", "")

    items = client.get("/api/inbox").json()
    assert [i["channel"] for i in items] == ["telegram_dm", "headhunter"]
    assert items[0]["contact"] == "hr_anna"
    assert items[0]["title"] == "Dev tg"
    assert items[1]["stage"] == "interview"

    response = client.post(
        "/api/applications/stage",
        json={"source": "headhunter", "external_id": "1", "stage": "offer"},
    )
    assert response.status_code == 200
    apps = client.get("/api/applications").json()
    assert {a["external_id"]: a["effective_stage"] for a in apps}["1"] == (
        "offer"
    )
    assert (
        client.post(
            "/api/applications/stage",
            json={"source": "headhunter", "external_id": "1", "stage": "x"},
        ).status_code
        == 400
    )
    assert client.get("/api/analytics/funnel").json()["offer"] == 1


def test_sync_hh_states_writes_log_and_notifies_only_real_replies(
    monkeypatch,
):
    import main

    with tempfile.TemporaryDirectory() as tmp:
        log = AppliedLog(Path(tmp) / "applied_log.json")
        for n in ("1", "2", "3"):
            log.record(_job(n), "", "", "applied", 8, [])
        monkeypatch.setattr(
            main,
            "list_negotiation_states",
            lambda driver: {
                "1": "Отказ",
                "2": "Просмотрен",
                "3": "Приглашение на интервью",
                "999": "Отказ",
            },
        )
        sent: list[str] = []
        monkeypatch.setattr(main, "notify", lambda p, text: sent.append(text))

        # Первая сверка — тихая загрузка истории одной сводкой.
        log.update_reply_state("headhunter", "2", "Не просмотрен")
        main._sync_headhunter_negotiation_states({}, None, log)
        assert len(sent) == 2

        stages = {
            e["external_id"]: effective_stage(e)
            for e in log.find_by_company("")
        }
        assert stages == {"1": "rejected", "2": None, "3": "interview"}
        assert len(sent) == 2  # "Просмотрен" — не ответ, без уведомления

        # Повторная сверка с теми же статусами ничего не шлёт.
        main._sync_headhunter_negotiation_states({}, None, log)
        assert len(sent) == 2


def test_market_endpoint(client):  # noqa: F811
    ctx = api.get_ctx()
    job = Job(
        role="Python Dev",
        company="Acme",
        source="habr_career",
        external_id="m1",
        salary="200 000 — 300 000 ₽",
        description="Python, Kubernetes. Remote from anywhere",
    )
    ctx.applied_log.record(job, "", "", "applied", 8, [])
    body = client.get("/api/analytics/market").json()
    assert body["salaries"][0]["currency"] == "RUB"
    assert {s["skill"] for s in body["skills"]} == {"Python", "Kubernetes"}
    assert body["regions"] == {"🌍 откуда угодно": 1}
