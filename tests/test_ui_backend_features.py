"""Доработки бэкенда под новый интерфейс (docs/UI_MAP.md, раздел 11):
каждая — добавка, старые данные и поведение по умолчанию не меняются."""

from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from src.webui import api
from tests.test_webui_api import client  # noqa: F401  (fixture)

# --- Уведомления: что присылать и история в приложении -------------------


def _params(tmp_path: Path, **extra) -> dict:
    secrets = tmp_path / "secrets.yaml"
    secrets.write_text(
        "notifications:\n"
        "  telegram_bot_token: 't'\n"
        "  telegram_chat_id: '1'\n",
        encoding="utf-8",
    )
    return {"secretsFile": secrets, "outputFileDirectory": tmp_path, **extra}


def test_notification_kind_by_category_and_text():
    from src.job_sources.telegram_notify import notification_kind

    assert notification_kind("HH: капча, нужен вход", "headhunter") == (
        "failure"
    )
    assert notification_kind("Откликнулся на 3 вакансии", "headhunter") == (
        "activity"
    )
    # Текст HR может содержать что угодно — тема решает.
    assert notification_kind("Ошибка в резюме?", "Ответы HR") == "activity"
    assert notification_kind("Осталось 1 ГБ", "Система") == "failure"


def test_muted_kind_is_not_sent_but_kept_in_history(tmp_path):
    from src.job_sources.telegram_notify import (
        notification_history,
        notify_from_secrets,
    )

    params = _params(tmp_path, notify={"failures": False})
    with patch(
        "src.job_sources.telegram_notify.send_notification"
    ) as send, patch(
        "src.job_sources.telegram_notify.get_or_create_topic",
        return_value=None,
    ):
        notify_from_secrets(params, "LinkedIn: капча", "linkedin")
        notify_from_secrets(params, "Откликнулся: Nova Tech", "linkedin")
    assert [c.args[2] for c in send.call_args_list] == [
        "Откликнулся: Nova Tech"
    ]
    history = notification_history(tmp_path)
    assert [(h["text"], h["status"]) for h in history] == [
        ("Откликнулся: Nova Tech", "sent"),
        ("LinkedIn: капча", "muted"),
    ]


def test_history_without_bot_marks_app_only(tmp_path):
    from src.job_sources.telegram_notify import (
        notification_history,
        notify_from_secrets,
    )

    secrets = tmp_path / "secrets.yaml"
    secrets.write_text("llm_api_key: 'x'\n", encoding="utf-8")
    notify_from_secrets(
        {"secretsFile": secrets, "outputFileDirectory": tmp_path},
        "Ответ HR @anna: добрый день",
        "Ответы HR",
    )
    (item,) = notification_history(tmp_path)
    assert item["status"] == "app" and item["kind"] == "activity"


def test_outreach_settings_notify_kinds_round_trip(client):  # noqa: F811
    body = client.get("/api/settings/outreach").json()
    assert body["notify_activity"] is True
    assert body["notify_failures"] is True
    response = client.post(
        "/api/settings/outreach", json={"notify_failures": False}
    )
    assert response.status_code == 200
    assert response.json()["notify_failures"] is False
    assert response.json()["notify_activity"] is True
    assert api.get_ctx().config["notify"]["failures"] is False


def test_notifications_endpoint_lists_newest_first(client):  # noqa: F811
    from src.job_sources.telegram_notify import record_notification

    params = {"outputFileDirectory": api.get_ctx().output_folder}
    record_notification(params, "первое", "headhunter", "activity", "sent")
    record_notification(params, "второе", "Система", "failure", "app")
    items = client.get("/api/notifications").json()["items"]
    assert [i["text"] for i in items] == ["второе", "первое"]


# --- Резервные копии: «Сделать копию сейчас» -----------------------------


def test_backup_now_creates_manual_copy_and_lists_it(client):  # noqa: F811
    out = api.get_ctx().output_folder
    (out / "applied_log.json").write_text(
        '{"applications": []}', encoding="utf-8"
    )
    response = client.post("/api/backups/now")
    assert response.status_code == 200
    body = response.json()
    manual = [b for b in body["backups"] if b["manual"]]
    assert [b["date"] for b in manual] == [body["date"]]
    assert (
        out.parent / "backups" / body["date"] / "applied_log.json"
    ).exists()


def test_backup_now_without_data_says_so(client):  # noqa: F811
    response = client.post("/api/backups/now")
    assert response.status_code == 409


def test_manual_backups_do_not_push_out_daily_ones(tmp_path):
    from datetime import date

    from src.utils.backup import KEEP_MANUAL, backup_now, daily_backup

    out = tmp_path / "output"
    out.mkdir()
    (out / "contact_book.json").write_text("{}", encoding="utf-8")
    daily_backup(out, date(2026, 10, 1))
    for i in range(KEEP_MANUAL + 3):
        backup_now(out, datetime(2026, 10, 2, 10, 0, i))
    daily_backup(out, date(2026, 10, 3))
    names = sorted(p.name for p in (tmp_path / "backups").iterdir())
    assert "2026-10-01" in names and "2026-10-03" in names
    assert len([n for n in names if len(n) > 10]) == KEEP_MANUAL


def test_restore_rejects_paths_outside_backups(client):  # noqa: F811
    response = client.post("/api/backups/restore", json={"date": "../output"})
    assert response.status_code == 400


# --- ИИ: порядок запасных провайдеров ------------------------------------


def test_llm_fallback_order_round_trip(client):  # noqa: F811
    assert client.get("/api/settings/llm").json()["fallback_order"] == []
    response = client.post(
        "/api/settings/llm", json={"fallback_order": ["groq", "gemini"]}
    )
    assert response.status_code == 200
    assert response.json()["fallback_order"] == ["groq", "gemini"]
    bad = client.post("/api/settings/llm", json={"fallback_order": ["nope"]})
    assert bad.status_code == 400


def test_fallback_order_puts_named_providers_first():
    from src.job_sources import llm_provider

    keys = {"openai": "a", "groq": "b", "gemini": "c", "mistral": "d"}
    built: list[str] = []

    def fake_build(provider, *args, **kwargs):
        built.append(provider)
        raise RuntimeError("не нужно строить")

    llm_provider.set_fallback_keys(keys)
    llm_provider.set_fallback_order(["mistral", "groq"])
    try:
        with patch.object(llm_provider, "_build_llm", side_effect=fake_build):
            llm_provider._build_fallback_llms("openai", 0)
    finally:
        llm_provider.set_fallback_keys({})
        llm_provider.set_fallback_order([])
    order = list(dict.fromkeys(built))
    assert order[:2] == ["mistral", "groq"]
    assert set(order) == {"mistral", "groq", "gemini"}


# --- Почта: свои правила письма ------------------------------------------


def test_letter_instructions_round_trip(client):  # noqa: F811
    text = "Пиши на «ты».\nУпомяни: готов к релокации"
    response = client.post(
        "/api/settings/outreach", json={"letter_instructions": text}
    )
    assert response.status_code == 200
    assert response.json()["letter_instructions"] == text
    assert api.get_ctx().config["direct"]["letter_instructions"] == text
