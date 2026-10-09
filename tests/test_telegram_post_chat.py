"""Чат «Новые вакансии из каналов»: пост парсера → черновик → отправка
с вашего аккаунта, «утром», скрыть, «не писать компании»."""

import json
from datetime import datetime, timedelta
from pathlib import Path

import src.webui.api as api
from src.job_sources.contact_book import ContactBook
from src.job_sources.telegram.watcher import (
    PENDING_SENDS_FILE,
    get_watch_post,
    save_watch_post,
    update_watch_post,
)
from src.job_sources.telegram_conversations import TelegramConversations
from tests.test_webui_api import client  # noqa: F401  (fixture)
from tests.test_webui_api import _with_telegram_creds

POST = {
    "channel": "rabotapython",
    "link": "https://t.me/rabotapython/1",
    "title": "Python-разработчик (Django)",
    "text": "Ищем Python-разработчика, удалённо. Пишите @anna_hr",
    "contacts": [{"kind": "telegram", "value": "anna_hr"}],
    "unverified": False,
}


class _FakeClient:
    sent: list = []

    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def send_message(self, contact, text):
        _FakeClient.sent.append(("text", contact, text))

    def send_file(self, contact, path):
        _FakeClient.sent.append(("file", contact, Path(path).name))


def _conversations(ctx) -> TelegramConversations:
    return TelegramConversations(
        ctx.output_folder / "telegram_conversations.json"
    )


def _post(ctx, **fields) -> str:
    post_id = save_watch_post(
        ctx.output_folder, {**POST, **fields.pop("post", {})}
    )
    if fields:
        update_watch_post(ctx.output_folder, post_id, **fields)
    return post_id


def test_resave_by_bot_keeps_status_and_found_at(tmp_path):
    post_id = save_watch_post(tmp_path, POST)
    found_at = get_watch_post(tmp_path, post_id)["found_at"]
    update_watch_post(tmp_path, post_id, status="sent")
    save_watch_post(tmp_path, POST)  # _deliver_via_bot пересохраняет
    post = get_watch_post(tmp_path, post_id)
    assert post["status"] == "sent"
    assert post["found_at"] == found_at


def test_posts_lists_only_recent_waiting_ones(client):  # noqa: F811
    ctx = api.get_ctx()
    fresh = _post(ctx)
    _post(ctx, post={"link": "https://t.me/rabotapython/2"}, status="sent")
    old = (datetime.now().astimezone() - timedelta(days=10)).isoformat()
    _post(ctx, post={"link": "https://t.me/rabotapython/3"}, found_at=old)
    _conversations(ctx).record_outbound("anna_hr", "Здравствуйте!")

    body = client.get("/api/telegram/posts").json()

    assert [p["id"] for p in body["posts"]] == [fresh]
    assert body["sent_today"] == 1
    assert body["daily_limit"] == 15
    assert body["posts"][0]["notes"]["anna_hr"].startswith("писали")


def test_send_goes_from_account_with_resume_and_closes_post(
    client, monkeypatch  # noqa: F811
):
    ctx = api.get_ctx()
    _with_telegram_creds(ctx)
    (ctx.config["dataFolder"] / "resume.pdf").write_bytes(b"%PDF-1.4")
    _FakeClient.sent = []
    monkeypatch.setattr(api, "TelegramSourceClient", _FakeClient)
    post_id = _post(ctx)

    res = client.post(
        f"/api/telegram/posts/{post_id}/send",
        json={
            "contact": "@anna_hr",
            "text": "Здравствуйте!",
            "resume": "resume.pdf",
        },
    )

    assert res.status_code == 200, res.text
    assert _FakeClient.sent == [
        ("text", "anna_hr", "Здравствуйте!"),
        ("file", "anna_hr", "resume.pdf"),
    ]
    conv = _conversations(ctx).get("anna_hr")
    assert conv["messages"][0]["job_link"] == POST["link"]
    assert get_watch_post(ctx.output_folder, post_id)["status"] == "sent"
    assert client.get("/api/telegram/posts").json()["posts"] == []


def test_send_refuses_contact_not_from_post(client, monkeypatch):  # noqa: F811
    ctx = api.get_ctx()
    _with_telegram_creds(ctx)
    _FakeClient.sent = []
    monkeypatch.setattr(api, "TelegramSourceClient", _FakeClient)
    post_id = _post(ctx)

    res = client.post(
        f"/api/telegram/posts/{post_id}/send",
        json={"contact": "someone_else", "text": "Привет"},
    )

    assert res.status_code == 400
    assert _FakeClient.sent == []


def test_later_queues_and_cancel_unqueues(client):  # noqa: F811
    # Бот для «утром» больше не нужен: очередь без шлюза разбирают проверка
    # ответов и окно приложения (main.flush_telegram_scheduled).
    ctx = api.get_ctx()
    post_id = _post(ctx)
    body = {"contact": "anna_hr", "text": "Здравствуйте!"}
    res = client.post(f"/api/telegram/posts/{post_id}/later", json=body)
    assert res.status_code == 200, res.text
    send_after = datetime.fromisoformat(res.json()["send_after"])
    assert send_after > datetime.now().astimezone() and send_after.hour == 10
    queue_file = ctx.output_folder / PENDING_SENDS_FILE
    queue = json.loads(queue_file.read_text(encoding="utf-8"))
    assert [e["contact"] for e in queue.values()] == ["anna_hr"]
    assert (
        client.get("/api/telegram/posts").json()["posts"][0]["status"]
        == "later"
    )

    client.post(
        f"/api/telegram/posts/{post_id}/status", json={"status": "new"}
    )
    assert json.loads(queue_file.read_text(encoding="utf-8")) == {}


def test_block_marks_company_do_not_contact(client):  # noqa: F811
    ctx = api.get_ctx()
    post_id = _post(ctx)

    res = client.post(
        f"/api/telegram/posts/{post_id}/status", json={"status": "blocked"}
    )

    assert res.status_code == 200
    cards = ContactBook(ctx.output_folder).all().values()
    assert any(card.get("do_not_contact") for card in cards)
    assert client.get("/api/telegram/posts").json()["posts"] == []


def test_history_falls_back_to_app_log_without_gateway(client):  # noqa: F811
    ctx = api.get_ctx()
    _conversations(ctx).record_outbound("anna_hr", "Здравствуйте!")

    body = client.get("/api/telegram/history/@anna_hr").json()

    assert body["source"] == "local"
    assert [m["text"] for m in body["messages"]] == ["Здравствуйте!"]
