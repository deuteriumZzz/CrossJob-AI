import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.webui import api


def _make_data_folder(tmp: str) -> Path:
    data_folder = Path(tmp) / "data_folder"
    data_folder.mkdir()
    (data_folder / "secrets.yaml").write_text(
        "llm_api_key: 'sk-test'\n", encoding="utf-8"
    )
    (data_folder / "work_preferences.yaml").write_text(
        "remote: true\n"
        "experience_level:\n"
        "  internship: false\n"
        "  entry: true\n"
        "  associate: true\n"
        "  mid_senior_level: true\n"
        "  director: false\n"
        "  executive: false\n"
        "job_types:\n"
        "  full_time: true\n"
        "  contract: false\n"
        "  part_time: false\n"
        "  temporary: false\n"
        "  internship: false\n"
        "  other: false\n"
        "  volunteer: false\n"
        "date:\n"
        "  all_time: false\n"
        "  month: false\n"
        "  week: false\n"
        "  24_hours: true\n"
        "positions: []\n"
        "locations: []\n"
        "distance: 10\n"
        "\n"
        "headhunter:\n"
        "  auto_apply: false\n"
        "  schedule_enabled: false\n"
        "  interval_hours: 3\n",
        encoding="utf-8",
    )
    return data_folder


@pytest.fixture
def client():
    with tempfile.TemporaryDirectory() as tmp:
        data_folder = _make_data_folder(tmp)
        api.set_data_folder(data_folder)
        yield TestClient(api.app)
        api.set_data_folder(Path("data_folder"))


def test_status_lists_all_sources_never_run(client):
    response = client.get("/api/status")
    assert response.status_code == 200
    body = response.json()
    assert body["daemon_running"] is False
    names = {s["name"] for s in body["sources"]}
    assert "headhunter" in names
    hh = next(s for s in body["sources"] if s["name"] == "headhunter")
    assert hh["status"] == "never_run"
    assert hh["schedule_enabled"] is False


def test_stats_empty_log_returns_zeros(client):
    response = client.get("/api/stats")
    assert response.json() == {"day": 0, "week": 0, "month": 0}


def test_settings_update_persists_and_reflects_in_status(client):
    response = client.post(
        "/api/settings",
        json={
            "source": "headhunter",
            "schedule_enabled": True,
            "interval_hours": 5,
        },
    )
    assert response.status_code == 200

    status = client.get("/api/status").json()
    hh = next(s for s in status["sources"] if s["name"] == "headhunter")
    assert hh["schedule_enabled"] is True
    assert hh["interval_hours"] == 5


def test_settings_update_rejects_unknown_source(client):
    response = client.post(
        "/api/settings", json={"source": "not_a_real_source"}
    )
    assert response.status_code == 400


def test_run_now_starts_selected_sources_and_reports_status(client):
    release = threading.Event()
    calls = []

    def fake_run_selected_sources(sources, parameters, llm_api_key):
        calls.append(sources)
        release.wait(timeout=5)

    with patch(
        "src.webui.api.run_selected_sources",
        side_effect=fake_run_selected_sources,
    ):
        response = client.post(
            "/api/run-now", json={"sources": ["headhunter", "superjob"]}
        )
        assert response.status_code == 200
        assert response.json() == {
            "started": True,
            "sources": ["headhunter", "superjob"],
        }

        status = client.get("/api/run-now/status").json()
        assert status["running"] is True
        assert set(status["sources"]) == {"headhunter", "superjob"}

        # Второй запуск, пока первый ещё идёт — конфликт.
        conflict = client.post("/api/run-now", json={"sources": ["zarplata"]})
        assert conflict.status_code == 409

        release.set()

    for _ in range(50):
        if not client.get("/api/run-now/status").json()["running"]:
            break
        time.sleep(0.05)
    assert calls == [["headhunter", "superjob"]]


def test_run_now_rejects_empty_and_unknown_sources(client):
    empty = client.post("/api/run-now", json={"sources": []})
    assert empty.status_code == 400

    unknown = client.post("/api/run-now", json={"sources": ["not_real"]})
    assert unknown.status_code == 400


def test_blacklist_candidates_empty_with_no_history(client):
    response = client.get("/api/analytics/blacklist-candidates")
    assert response.json() == []


def test_notifications_test_requires_config(client):
    response = client.post("/api/notifications/test")
    assert response.status_code == 400


def test_notifications_test_sends_and_reports_success(client):
    secrets_file = api.get_ctx().secrets_file
    secrets_file.write_text(
        secrets_file.read_text(encoding="utf-8")
        + "\nnotifications:\n"
        + "  telegram_bot_token: 'BOT'\n"
        + "  telegram_chat_id: '123'\n",
        encoding="utf-8",
    )

    with patch("src.webui.api.send_notification") as mock_send:
        response = client.post("/api/notifications/test")

    assert response.status_code == 200
    assert response.json() == {"sent": True}
    mock_send.assert_called_once()
    assert mock_send.call_args.args[0] == "BOT"
    assert mock_send.call_args.args[1] == "123"


def test_notifications_test_reports_send_failure(client):
    secrets_file = api.get_ctx().secrets_file
    secrets_file.write_text(
        secrets_file.read_text(encoding="utf-8")
        + "\nnotifications:\n"
        + "  telegram_bot_token: 'BOT'\n"
        + "  telegram_chat_id: '123'\n",
        encoding="utf-8",
    )

    with patch(
        "src.webui.api.send_notification", side_effect=RuntimeError("boom")
    ):
        response = client.post("/api/notifications/test")

    assert response.status_code == 502


def test_logs_endpoint_reports_disabled_file_logging(client):
    response = client.get("/api/logs")
    body = response.json()
    assert body["lines"] == []
    assert body["note"] is not None


def test_daemon_start_and_stop(client):
    start = client.post("/api/daemon/start")
    assert start.json() == {"running": True}

    status = client.get("/api/status").json()
    assert status["daemon_running"] is True

    stop = client.post("/api/daemon/stop")
    assert stop.json() == {"running": False}


def test_generate_styles_returns_style_names(client):
    response = client.get("/api/generate/styles")
    assert response.status_code == 200
    assert "Default" in response.json()


def test_generate_resume_tailored_requires_job_url(client):
    response = client.post("/api/generate/resume-tailored", json={})
    assert response.status_code == 400


def test_generate_unknown_kind_is_404(client):
    response = client.post("/api/generate/not-a-kind", json={})
    assert response.status_code == 404


def test_generate_resume_runs_and_reports_status(client):
    release = threading.Event()
    calls = []

    def fake_create_resume_pdf(config, llm_api_key, style_name=None):
        calls.append(style_name)
        release.wait(timeout=5)
        return Path("/tmp/resume_base.pdf")

    with patch(
        "src.webui.api._create_resume_pdf",
        side_effect=fake_create_resume_pdf,
    ):
        response = client.post(
            "/api/generate/resume", json={"style_name": "Default"}
        )
        assert response.status_code == 200

        status = client.get("/api/generate/status").json()
        assert status["running"] is True

        conflict = client.post("/api/generate/resume", json={})
        assert conflict.status_code == 409

        release.set()

    for _ in range(50):
        if not client.get("/api/generate/status").json()["running"]:
            break
        time.sleep(0.05)
    assert calls == ["Default"]
    final = client.get("/api/generate/status").json()
    assert final["ready"] is True
    assert final["path"] == "/tmp/resume_base.pdf"


def test_generate_reports_error_from_generator(client):
    def fake_create_resume_pdf(config, llm_api_key, style_name=None):
        raise RuntimeError("Selenium boom")

    with patch(
        "src.webui.api._create_resume_pdf",
        side_effect=fake_create_resume_pdf,
    ):
        client.post("/api/generate/resume", json={})
        for _ in range(50):
            if not client.get("/api/generate/status").json()["running"]:
                break
            time.sleep(0.05)
    final = client.get("/api/generate/status").json()
    assert final["error"] == "Selenium boom"


def test_generate_download_without_result_is_404(client):
    response = client.get("/api/generate/download")
    assert response.status_code == 404


def test_usage_endpoint_reports_zero_when_no_calls_made(client):
    response = client.get("/api/usage")
    assert response.status_code == 200
    assert response.json()["today_tokens"] == 0
