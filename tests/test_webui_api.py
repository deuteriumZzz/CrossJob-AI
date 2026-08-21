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


def test_settings_update_per_source_job_max_applications(client):
    from config import JOB_MAX_APPLICATIONS

    unset = client.get("/api/status").json()
    hh = next(s for s in unset["sources"] if s["name"] == "headhunter")
    sj = next(s for s in unset["sources"] if s["name"] == "superjob")
    assert hh["job_max_applications"] == JOB_MAX_APPLICATIONS
    assert sj["job_max_applications"] == JOB_MAX_APPLICATIONS

    response = client.post(
        "/api/settings",
        json={"source": "headhunter", "job_max_applications": 20},
    )
    assert response.status_code == 200

    status = client.get("/api/status").json()
    hh = next(s for s in status["sources"] if s["name"] == "headhunter")
    sj = next(s for s in status["sources"] if s["name"] == "superjob")
    assert hh["job_max_applications"] == 20
    # другая площадка не затронута
    assert sj["job_max_applications"] == JOB_MAX_APPLICATIONS


def test_settings_update_rejects_job_max_applications_below_one(client):
    response = client.post(
        "/api/settings",
        json={"source": "headhunter", "job_max_applications": 0},
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


def test_refresh_plain_text_resume_endpoint(client):
    with patch(
        "src.webui.api._refresh_plain_text",
        return_value=Path("/tmp/plain_text_resume.yaml"),
    ):
        response = client.post("/api/resume/refresh-plain-text")

    assert response.status_code == 200
    assert response.json()["refreshed"] is True


def test_refresh_plain_text_resume_endpoint_missing_pdf(client):
    with patch(
        "src.webui.api._refresh_plain_text",
        side_effect=FileNotFoundError("no resume.pdf"),
    ):
        response = client.post("/api/resume/refresh-plain-text")

    assert response.status_code == 400


def test_setup_status_not_needed_when_data_folder_valid(client):
    response = client.get("/api/setup/status")
    assert response.status_code == 200
    assert response.json() == {"needs_setup": False}


def test_setup_status_needed_when_data_folder_missing():
    with tempfile.TemporaryDirectory() as tmp:
        data_folder = Path(tmp) / "data_folder"
        api.set_data_folder(data_folder)
        try:
            fresh_client = TestClient(api.app)
            response = fresh_client.get("/api/setup/status")
            assert response.json() == {"needs_setup": True}
        finally:
            api.set_data_folder(Path("data_folder"))


def test_other_endpoints_return_428_when_data_folder_missing():
    with tempfile.TemporaryDirectory() as tmp:
        data_folder = Path(tmp) / "data_folder"
        api.set_data_folder(data_folder)
        try:
            fresh_client = TestClient(api.app)
            response = fresh_client.get("/api/status")
            assert response.status_code == 428
        finally:
            api.set_data_folder(Path("data_folder"))


def test_setup_init_creates_data_folder_and_becomes_ready():
    with tempfile.TemporaryDirectory() as tmp:
        data_folder = Path(tmp) / "data_folder"
        api.set_data_folder(data_folder)
        try:
            fresh_client = TestClient(api.app)
            response = fresh_client.post(
                "/api/setup/init", json={"api_key": "sk-web-wizard"}
            )
            assert response.status_code == 200
            body = response.json()
            assert body["created_folder"] is True
            assert body["api_key_written"] is True
            assert body["ready"] is True

            status = fresh_client.get("/api/setup/status")
            assert status.json() == {"needs_setup": False}

            secrets_text = (data_folder / "secrets.yaml").read_text(
                encoding="utf-8"
            )
            assert "llm_api_key: 'sk-web-wizard'" in secrets_text
        finally:
            api.set_data_folder(Path("data_folder"))


def test_get_limits_settings_defaults_to_config_values(client):
    from config import DAILY_APPLICATION_LIMIT

    response = client.get("/api/settings/limits")
    assert response.status_code == 200
    assert response.json()["daily_application_limit"] == (
        DAILY_APPLICATION_LIMIT
    )


def test_post_limits_settings_updates_and_persists(client):
    response = client.post(
        "/api/settings/limits",
        json={
            "daily_application_limit": 30,
            "linkedin_daily_application_limit": 10,
            "job_max_applications": 9,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["daily_application_limit"] == 30
    assert body["linkedin_daily_application_limit"] == 10
    assert body["job_max_applications"] == 9

    follow_up = client.get("/api/settings/limits")
    assert follow_up.json() == body


def test_post_limits_settings_rejects_values_below_one(client):
    response = client.post(
        "/api/settings/limits", json={"job_max_applications": 0}
    )
    assert response.status_code == 400


def test_post_limits_settings_partial_update_leaves_others_unchanged(
    client,
):
    client.post("/api/settings/limits", json={"daily_application_limit": 25})
    response = client.post(
        "/api/settings/limits", json={"job_max_applications": 7}
    )
    body = response.json()
    assert body["daily_application_limit"] == 25
    assert body["job_max_applications"] == 7


def test_post_limits_settings_llm_cost_alert(client):
    response = client.post(
        "/api/settings/limits", json={"llm_daily_cost_alert_usd": 2.5}
    )
    assert response.status_code == 200
    assert response.json()["llm_daily_cost_alert_usd"] == 2.5


def test_post_limits_settings_rejects_zero_llm_cost_alert(client):
    response = client.post(
        "/api/settings/limits", json={"llm_daily_cost_alert_usd": 0}
    )
    assert response.status_code == 400


def test_export_applied_log_returns_404_when_no_history(client):
    response = client.get("/api/export/applied-log")
    assert response.status_code == 404


def test_export_applied_log_downloads_json_backup(client):
    ctx = api.get_ctx()
    ctx.applied_log.path.parent.mkdir(parents=True, exist_ok=True)
    ctx.applied_log.path.write_text('{"applications": []}', encoding="utf-8")

    response = client.get("/api/export/applied-log")
    assert response.status_code == 200
    assert response.json() == {"applications": []}
    assert "applied_log_backup_" in response.headers["content-disposition"]


def test_get_llm_settings_defaults_to_config(client):
    response = client.get("/api/settings/llm")
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "openai"
    assert body["model"] == "gpt-4o-mini"
    assert "groq" in body["models"]
    assert body["api_key_previews"]["openai"]
    assert "sk-test" not in body["api_key_previews"]["openai"]


def test_post_llm_settings_switches_provider(client):
    response = client.post(
        "/api/settings/llm",
        json={"provider": "groq", "model": "llama-3.3-70b-versatile"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "groq"
    assert body["model"] == "llama-3.3-70b-versatile"

    follow_up = client.get("/api/settings/llm")
    assert follow_up.json()["provider"] == "groq"
    # Легаси llm_api_key (secrets.yaml fixture, "sk-test") заведён для
    # openai — переключение на groq без своего сохранённого ключа не
    # должно тихо показывать/использовать чужой ключ.
    assert "groq" not in follow_up.json()["api_key_previews"]


def test_post_llm_settings_rejects_unknown_provider(client):
    response = client.post(
        "/api/settings/llm", json={"provider": "not-a-real-provider"}
    )
    assert response.status_code == 400


def test_post_llm_key_updates_secrets_and_masks_response(client):
    response = client.post(
        "/api/settings/llm-key",
        json={"provider": "groq", "api_key": "sk-brand-new-key-12345"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "groq"
    assert "sk-brand-new-key-12345" not in body["api_key_preview"]
    assert body["api_key_preview"].startswith("sk-b")

    secrets_text = api.get_ctx().secrets_file.read_text(encoding="utf-8")
    assert "sk-brand-new-key-12345" in secrets_text
    assert "llm_api_keys" in secrets_text

    follow_up = client.get("/api/settings/llm")
    assert follow_up.json()["api_key_previews"]["groq"].startswith("sk-b")


def test_post_llm_key_rejects_empty_key(client):
    response = client.post(
        "/api/settings/llm-key", json={"provider": "groq", "api_key": "   "}
    )
    assert response.status_code == 400


def test_post_llm_key_rejects_unknown_provider(client):
    response = client.post(
        "/api/settings/llm-key",
        json={"provider": "not-a-real-provider", "api_key": "sk-x"},
    )
    assert response.status_code == 400
