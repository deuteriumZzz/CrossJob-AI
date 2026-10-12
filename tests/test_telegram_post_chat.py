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
    remember_telegram_post_contact,
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


def test_history_includes_legacy_sent_and_old_posts_but_not_source_deletions(
    client,  # noqa: F811
):  # noqa: F811
    ctx = api.get_ctx()
    legacy_id = _post(ctx)
    update_watch_post(ctx.output_folder, legacy_id, found_at="")
    old = (datetime.now().astimezone() - timedelta(days=30)).isoformat()
    sent_id = _post(
        ctx,
        post={"link": "https://t.me/rabotapython/2"},
        found_at=old,
        status="sent",
    )
    deleted_id = _post(
        ctx,
        post={"link": "https://t.me/rabotapython/3"},
        status="source_deleted",
    )

    body = client.get("/api/telegram/posts?scope=all&limit=1").json()
    assert body["total"] == 2
    assert [post["id"] for post in body["posts"]] == [sent_id]
    next_page = client.get(
        "/api/telegram/posts?scope=all&limit=1&offset=1"
    ).json()
    assert [post["id"] for post in next_page["posts"]] == [legacy_id]
    assert deleted_id not in [post["id"] for post in body["posts"]]
    assert client.get("/api/telegram/posts").json()["posts"] == []


def test_first_message_drafts_for_same_contact_keep_each_post(tmp_path):
    from src.job_sources.hr_replies import DraftStore

    store = DraftStore(tmp_path / "drafts.json")
    first = store.add(
        "anna_hr",
        "Message for first vacancy",
        "first",
        "post-one",
        post_id="1",
    )
    second = store.add(
        "anna_hr",
        "Message for second vacancy",
        "first",
        "post-two",
        post_id="2",
    )

    assert set(store.all()) == {first, second}


def test_many_starter_drafts_do_not_overwrite_on_code_collision(
    tmp_path, monkeypatch
):
    import src.job_sources.hr_replies as hr_replies
    from src.job_sources.hr_replies import DraftStore

    store = DraftStore(tmp_path / "drafts.json")
    first = store.add("anna_hr", "First", "first", "post-one", post_id="1")
    codes = iter((first, "cafe"))
    monkeypatch.setattr(hr_replies.secrets, "token_hex", lambda _: next(codes))
    second = store.add("anna_hr", "Second", "first", "post-two", post_id="2")
    assert second == "cafe"
    assert set(store.all()) == {first, second}


def test_history_prepares_starter_draft_once_for_each_actionable_post(
    client,  # noqa: F811
):  # noqa: F811
    ctx = api.get_ctx()
    first = _post(ctx)
    second = _post(ctx, post={"link": "https://t.me/rabotapython/2"})
    update_watch_post(ctx.output_folder, first, found_at="")

    first_page = client.get("/api/telegram/posts?scope=all").json()
    drafts = {post["id"]: post["draft"] for post in first_page["posts"]}
    assert drafts[first]["text"]
    assert drafts[second]["text"]
    assert drafts[first]["code"] != drafts[second]["code"]
    assert drafts[first]["source"] == "template"
    again = client.get("/api/telegram/posts?scope=all").json()
    assert {post["id"]: post["draft"]["code"] for post in again["posts"]} == {
        first: drafts[first]["code"],
        second: drafts[second]["code"],
    }


def test_explicit_ai_rewrite_requires_key_and_preserves_starter_draft(
    client, monkeypatch  # noqa: F811
):
    ctx = api.get_ctx()
    post_id = _post(ctx)
    starter = client.get("/api/telegram/posts?scope=all").json()["posts"][0][
        "draft"
    ]
    monkeypatch.setattr(ctx, "llm_api_key", "")
    response = client.post(
        f"/api/telegram/posts/{post_id}/draft",
        json={"contact": "anna_hr", "rewrite": True},
    )
    assert response.status_code == 400
    assert "ИИ" in response.json()["detail"]
    current = client.get("/api/telegram/posts?scope=all").json()["posts"][0]
    assert current["draft"]["code"] == starter["code"]
    assert current["draft"]["text"] == starter["text"]


def test_explicit_ai_rewrite_failure_preserves_previous_draft(
    client, monkeypatch  # noqa: F811
):
    ctx = api.get_ctx()
    post_id = _post(ctx)
    starter = client.get("/api/telegram/posts?scope=all").json()["posts"][0][
        "draft"
    ]
    monkeypatch.setattr(ctx, "llm_api_key", "test-key")

    def unavailable(*args, **kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(api, "generate_first_message", unavailable)
    response = client.post(
        f"/api/telegram/posts/{post_id}/draft",
        json={"contact": "anna_hr", "rewrite": True},
    )
    assert response.status_code == 502
    assert "ИИ" in response.json()["detail"]
    current = client.get("/api/telegram/posts?scope=all").json()["posts"][0]
    assert current["draft"]["code"] == starter["code"]
    assert current["draft"]["text"] == starter["text"]


def test_explicit_ai_rewrite_ignores_disabled_smart_greeting(
    client, monkeypatch  # noqa: F811
):
    ctx = api.get_ctx()
    post_id = _post(ctx)
    ctx.config["telegram"]["smart_greeting"] = False
    monkeypatch.setattr(ctx, "llm_api_key", "test-key")
    calls = []

    def generated(*args, **kwargs):
        calls.append(args)
        return {"subject": "", "text": "Персональное письмо"}

    monkeypatch.setattr(api, "generate_first_message", generated)
    response = client.post(
        f"/api/telegram/posts/{post_id}/draft",
        json={"contact": "anna_hr", "rewrite": True},
    )
    assert response.status_code == 200, response.text
    assert response.json()["source"] == "ai"
    assert response.json()["rewritten"] is True
    assert response.json()["text"] == "Персональное письмо"
    assert len(calls) == 1


def test_manual_post_contact_is_validated_and_not_duplicated(
    client,  # noqa: F811
):
    ctx = api.get_ctx()
    post_id = _post(
        ctx, post={"contacts": [], "text": "Ищем разработчика без адреса"}
    )
    endpoint = f"/api/telegram/posts/{post_id}/contacts"

    invalid = client.post(endpoint, json={"kind": "telegram", "value": "@bad"})
    assert invalid.status_code == 400
    invalid_email = client.post(
        endpoint, json={"kind": "email", "value": "not-an-email"}
    )
    assert invalid_email.status_code == 400
    invalid_kind = client.post(
        endpoint, json={"kind": "phone", "value": "1234567890"}
    )
    assert invalid_kind.status_code == 400
    assert get_watch_post(ctx.output_folder, post_id)["contacts"] == []

    first = client.post(
        endpoint, json={"kind": "telegram", "value": "@nextbit_hr"}
    )
    assert first.status_code == 200, first.text
    assert first.json()["contacts"] == [
        {"kind": "telegram", "value": "nextbit_hr", "source": "manual"}
    ]
    saved = get_watch_post(ctx.output_folder, post_id)
    assert saved["recipient_options"] == [
        {"kind": "telegram", "value": "nextbit_hr", "source": "manual"}
    ]
    from src.webui.api import TelegramPostSend, _telegram_post_send_args

    contact, text, resume = _telegram_post_send_args(
        ctx,
        saved,
        TelegramPostSend(contact="@nextbit_hr", text="Привет"),
    )
    assert (contact, text, resume) == ("nextbit_hr", "Привет", None)
    repeated = client.post(
        endpoint, json={"kind": "telegram", "value": "NEXTBIT_HR"}
    )
    assert repeated.status_code == 200
    assert repeated.json()["contacts"] == first.json()["contacts"]
    email = client.post(
        endpoint, json={"kind": "email", "value": "Jobs@Example.COM"}
    )
    assert email.status_code == 200, email.text
    assert [item["kind"] for item in email.json()["contacts"]] == [
        "telegram",
        "email",
    ]
    assert email.json()["contacts"][1]["value"] == "Jobs@example.com"
    assert (
        get_watch_post(ctx.output_folder, post_id)["contacts"]
        == email.json()["contacts"]
    )


def test_manual_contact_rejects_deleted_post(client):  # noqa: F811
    ctx = api.get_ctx()
    for status in ("removed", "source_deleted"):
        post_id = _post(
            ctx,
            post={"link": f"https://t.me/rabotapython/{status}"},
            status=status,
        )
        response = client.post(
            f"/api/telegram/posts/{post_id}/contacts",
            json={"kind": "telegram", "value": "@nextbit_hr"},
        )
        assert response.status_code == 409
        assert (
            get_watch_post(ctx.output_folder, post_id)["contacts"]
            == POST["contacts"]
        )


def test_draft_does_not_fall_back_to_different_recipient(
    client,  # noqa: F811
):
    ctx = api.get_ctx()
    post_id = _post(ctx)
    response = client.post(
        f"/api/telegram/posts/{post_id}/draft",
        json={"contact": "wrong_hr", "rewrite": True},
    )
    assert response.status_code == 400
    assert "контакта нет" in response.json()["detail"]


def test_ambiguous_post_requires_explicit_safe_recipient(
    client,  # noqa: F811
):
    ctx = api.get_ctx()
    post_id = _post(
        ctx,
        post={
            "text": "Команда @alpha_hr и канал @beta_jobs обсуждают вакансию",
            "contacts": [
                {"kind": "telegram", "value": "alpha_hr"},
                {"kind": "telegram", "value": "beta_jobs"},
            ],
        },
    )
    post = get_watch_post(ctx.output_folder, post_id)
    assert post["recipient_options"] == []
    assert (
        client.post(
            f"/api/telegram/posts/{post_id}/draft", json={}
        ).status_code
        == 409
    )
    response = client.post(
        f"/api/telegram/posts/{post_id}/draft",
        json={"contact": "alpha_hr"},
    )
    assert response.status_code == 400
    assert (
        client.get("/api/telegram/posts?scope=all").json()["posts"][0]["draft"]
        is None
    )
    send = client.post(
        f"/api/telegram/posts/{post_id}/send",
        json={"contact": "alpha_hr", "text": "Привет", "resume": ""},
    )
    assert send.status_code == 400
    later = client.post(
        f"/api/telegram/posts/{post_id}/later",
        json={"contact": "alpha_hr", "text": "Привет", "resume": ""},
    )
    assert later.status_code == 400


def test_post_list_backfills_hirify_history_without_sending(
    client,  # noqa: F811
):
    ctx = api.get_ctx()
    link = "https://hirify.me/jobs/7-python-dev"
    ContactBook(ctx.output_folder).add(
        "Ромашка",
        [
            {
                "kind": "telegram",
                "value": "nextbit_hr",
                "source": "Hirify: контакты",
                "source_url": link,
            }
        ],
        vacancy={
            "source": "hirify",
            "link": link,
            "title": "Python Developer",
            "text": "Отклик через найденные контакты",
        },
    )

    response = client.get("/api/telegram/posts?scope=all")
    assert response.status_code == 200, response.text
    posts = response.json()["posts"]
    assert len(posts) == 1
    assert posts[0]["source"] == "hirify"
    assert posts[0]["recipient_options"] == [
        {"kind": "telegram", "value": "nextbit_hr", "source": "hirify"}
    ]
    assert client.get("/api/telegram/posts?scope=all").json()["total"] == 1
    assert not list(ctx.output_folder.glob("*pending*"))


def test_removed_contact_cannot_be_selected_when_other_recipient_remains(
    client,  # noqa: F811
):
    ctx = api.get_ctx()
    post_id = _post(
        ctx,
        post={
            "text": "Связь: @anna_hr\nСвязь: @other_hr",
            "contacts": [
                {"kind": "telegram", "value": "anna_hr"},
                {"kind": "telegram", "value": "other_hr"},
            ],
        },
    )
    _conversations(ctx).dismiss_local("anna_hr")
    posts = client.get("/api/telegram/posts?scope=all").json()["posts"]
    assert [item["value"] for item in posts[0]["recipient_options"]] == [
        "other_hr"
    ]
    draft = client.post(
        f"/api/telegram/posts/{post_id}/draft",
        json={"contact": "anna_hr"},
    )
    assert draft.status_code == 400
    later = client.post(
        f"/api/telegram/posts/{post_id}/later",
        json={"contact": "anna_hr", "text": "Привет", "resume": ""},
    )
    assert later.status_code == 400


def test_telegram_dialog_history_loads_more_than_forty_messages(
    client, monkeypatch  # noqa: F811
):  # noqa: F811
    ctx = api.get_ctx()
    _with_telegram_creds(ctx)
    (ctx.output_folder / ".telegram_session.session").touch()
    _post(ctx)
    seen = []

    class HistoryClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def dialog_history(self, contact, limit=40):
            seen.append((contact, limit))
            return [
                {
                    "id": i,
                    "direction": "in",
                    "text": f"Message {i}",
                    "at": "2026-10-01T10:00:00Z",
                }
                for i in range(81)
            ]

    monkeypatch.setattr(api, "TelegramSourceClient", HistoryClient)
    response = client.get("/api/telegram/history/anna_hr").json()
    assert response["source"] == "telegram"
    assert len(response["messages"]) == 81
    assert seen == [("anna_hr", 200)]


def test_telegram_dialog_history_can_load_older_pages(
    client, monkeypatch  # noqa: F811
):  # noqa: F811
    ctx = api.get_ctx()
    _with_telegram_creds(ctx)
    (ctx.output_folder / ".telegram_session.session").touch()
    seen = []

    class HistoryClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def dialog_history(self, contact, limit=200, before_id=0):
            seen.append((contact, limit, before_id))
            return [{"id": 4, "text": "Older", "direction": "in"}]

    monkeypatch.setattr(api, "TelegramSourceClient", HistoryClient)
    response = client.get("/api/telegram/history/anna_hr?before_id=5").json()
    assert response["messages"][0]["id"] == 4
    assert response["has_more"] is False
    assert seen == [("anna_hr", 200, 5)]


def test_existing_parser_contact_dialog_is_visible_without_local_journal(
    client, monkeypatch  # noqa: F811
):  # noqa: F811
    ctx = api.get_ctx()
    _with_telegram_creds(ctx)
    (ctx.output_folder / ".telegram_session.session").touch()
    _post(ctx)

    class DialogClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def dialog_summaries(self, relevant_contacts):
            assert "anna_hr" in relevant_contacts
            return [
                {
                    "contact": "anna_hr",
                    "last_activity_at": "2026-10-01T10:00:00Z",
                    "last_message": {
                        "direction": "in",
                        "text": "Reply",
                        "at": "2026-10-01T10:00:00Z",
                    },
                    "message_count": 81,
                    "unread": False,
                }
            ]

    monkeypatch.setattr(api, "TelegramSourceClient", DialogClient)
    body = client.get("/api/telegram/conversations").json()
    assert [dialog["contact"] for dialog in body] == ["anna_hr"]
    assert _conversations(ctx).already_contacted("anna_hr")
    opened = client.get("/api/telegram/conversations/anna_hr")
    assert opened.status_code == 200
    assert opened.json()["messages"] == []


def test_remote_dialog_deletion_clears_local_copy(
    client, monkeypatch  # noqa: F811
):  # noqa: F811
    ctx = api.get_ctx()
    _with_telegram_creds(ctx)
    (ctx.output_folder / ".telegram_session.session").touch()
    _conversations(ctx).record_outbound("anna_hr", "Hello")

    class DialogClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def dialog_summaries(self, relevant_contacts):
            assert "anna_hr" in relevant_contacts
            return []

    monkeypatch.setattr(api, "TelegramSourceClient", DialogClient)
    assert client.get("/api/telegram/conversations").json() == []
    reloaded = _conversations(ctx)
    assert reloaded.get("anna_hr") is None
    assert reloaded.already_contacted("anna_hr")


def test_delete_dialog_removes_it_in_telegram_and_locally(
    client, monkeypatch  # noqa: F811
):  # noqa: F811
    ctx = api.get_ctx()
    _with_telegram_creds(ctx)
    (ctx.output_folder / ".telegram_session.session").touch()
    _conversations(ctx).record_outbound("anna_hr", "Hello")
    deleted = []

    class DialogClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def delete_dialog(self, contact):
            deleted.append(contact)

    monkeypatch.setattr(api, "TelegramSourceClient", DialogClient)
    response = client.delete("/api/telegram/conversations/anna_hr")
    assert response.status_code == 200
    assert deleted == ["anna_hr"]
    reloaded = _conversations(ctx)
    assert reloaded.get("anna_hr") is None
    assert reloaded.already_contacted("anna_hr")


def test_deleting_dialog_preserves_already_contacted_safety(tmp_path):
    conversations = TelegramConversations(tmp_path / "conversations.json")
    conversations.record_outbound("anna_hr", "Hello")
    assert conversations.delete("anna_hr")
    reloaded = TelegramConversations(tmp_path / "conversations.json")
    assert reloaded.all() == []
    assert reloaded.already_contacted("anna_hr")


def test_backup_includes_parser_history_and_pending_sends(tmp_path):
    from src.utils.backup import backup_now

    output = tmp_path / "output"
    output.mkdir()
    names = (
        ".watch_posts.json",
        ".pending_telegram_sends.json",
        ".telegram_backfilled_channels.json",
        ".night_posts.json",
    )
    for name in names:
        (output / name).write_text("{}", encoding="utf-8")
    backup = backup_now(output)
    assert all((backup / name).exists() for name in names)


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
    assert res.json()["resume_status"] == "sent"
    assert res.json()["resume_name"] == "resume.pdf"
    conv = _conversations(ctx).get("anna_hr")
    assert conv["messages"][0]["job_link"] == POST["link"]
    saved = get_watch_post(ctx.output_folder, post_id)
    assert saved["status"] == "sent"
    assert saved["resume_status"] == "sent"
    assert saved["resume_name"] == "resume.pdf"
    assert _conversations(ctx).sent_today_count() == 1
    assert client.get("/api/telegram/posts").json()["posts"] == []


def test_resume_uses_same_telegram_session_as_message(
    client, monkeypatch  # noqa: F811
):
    ctx = api.get_ctx()
    _with_telegram_creds(ctx)
    (ctx.config["dataFolder"] / "resume.pdf").write_bytes(b"%PDF-1.4")
    post_id = _post(ctx)
    sessions = []

    class OneSessionClient(_FakeClient):
        def __enter__(self):
            sessions.append(self)
            return self

    OneSessionClient.sent = []
    monkeypatch.setattr(api, "TelegramSourceClient", OneSessionClient)

    result = client.post(
        f"/api/telegram/posts/{post_id}/send",
        json={"contact": "anna_hr", "text": "Привет", "resume": "resume.pdf"},
    )

    assert result.status_code == 200, result.text
    assert len(sessions) == 1
    assert result.json()["resume_status"] == "sent"


def test_resume_failure_reports_partial_send_without_retrying_text(
    client, monkeypatch  # noqa: F811
):
    ctx = api.get_ctx()
    _with_telegram_creds(ctx)
    (ctx.config["dataFolder"] / "resume.pdf").write_bytes(b"%PDF-1.4")
    post_id = _post(ctx)

    class FileFailureClient(_FakeClient):
        def send_file(self, contact, path):
            raise RuntimeError("вложение отклонено")

    _FakeClient.sent = []
    monkeypatch.setattr(api, "TelegramSourceClient", FileFailureClient)
    body = {"contact": "anna_hr", "text": "Привет", "resume": "resume.pdf"}
    first = client.post(f"/api/telegram/posts/{post_id}/send", json=body)
    again = client.post(f"/api/telegram/posts/{post_id}/send", json=body)

    assert first.status_code == 200, first.text
    assert first.json()["resume_status"] == "failed"
    assert "Текст ушёл, резюме — нет" in first.json()["warning"]
    assert again.status_code == 409
    assert _FakeClient.sent == [("text", "anna_hr", "Привет")]
    saved = get_watch_post(ctx.output_folder, post_id)
    assert saved["status"] == "sent"
    assert saved["resume_status"] == "failed"
    assert saved["resume_name"] == "resume.pdf"


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


def test_sent_or_queued_post_cannot_send_again(
    client, monkeypatch  # noqa: F811
):  # noqa: F811
    ctx = api.get_ctx()
    _with_telegram_creds(ctx)
    _FakeClient.sent = []
    monkeypatch.setattr(api, "TelegramSourceClient", _FakeClient)
    post_id = _post(ctx)
    for status in ("sent", "queued", "source_deleted"):
        update_watch_post(ctx.output_folder, post_id, status=status)
        response = client.post(
            f"/api/telegram/posts/{post_id}/send",
            json={"contact": "anna_hr", "text": "Hello"},
        )
        assert response.status_code == 409
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


def test_blocked_scheduled_post_does_not_send_later(client):  # noqa: F811
    ctx = api.get_ctx()
    post_id = _post(ctx)
    body = {"contact": "anna_hr", "text": "Здравствуйте!"}
    queued = client.post(f"/api/telegram/posts/{post_id}/later", json=body)
    assert queued.status_code == 200
    blocked = client.post(
        f"/api/telegram/posts/{post_id}/status",
        json={"status": "blocked"},
    )
    assert blocked.status_code == 200
    assert (
        json.loads(
            (ctx.output_folder / PENDING_SENDS_FILE).read_text(
                encoding="utf-8"
            )
        )
        == {}
    )


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


def test_remove_post_locally_survives_resync_and_cancels_pending_send(
    client,  # noqa: F811
):  # noqa: F811
    ctx = api.get_ctx()
    post_id = _post(ctx)
    queued = client.post(
        f"/api/telegram/posts/{post_id}/later",
        json={"contact": "anna_hr", "text": "Здравствуйте!"},
    )
    assert queued.status_code == 200, queued.text

    removed = client.delete(f"/api/telegram/posts/{post_id}")
    assert removed.status_code == 200, removed.text
    assert removed.json() == {"removed": post_id}
    assert get_watch_post(ctx.output_folder, post_id)["status"] == "removed"
    assert client.get("/api/telegram/posts?scope=all").json()["posts"] == []
    assert (
        json.loads(
            (ctx.output_folder / PENDING_SENDS_FILE).read_text(
                encoding="utf-8"
            )
        )
        == {}
    )

    save_watch_post(ctx.output_folder, {**POST, "status": "new"})
    assert get_watch_post(ctx.output_folder, post_id)["status"] == "removed"
    assert client.get("/api/telegram/posts?scope=all").json()["total"] == 0
    assert (
        client.post(
            f"/api/telegram/posts/{post_id}/status", json={"status": "new"}
        ).status_code
        == 409
    )


def test_remove_contact_locally_hides_its_posts_and_remote_dialog(
    client, monkeypatch  # noqa: F811
):  # noqa: F811
    ctx = api.get_ctx()
    _with_telegram_creds(ctx)
    (ctx.output_folder / ".telegram_session.session").touch()
    removed_post = _post(ctx)
    kept_post = _post(
        ctx,
        post={
            "link": "https://t.me/rabotapython/2",
            "contacts": [{"kind": "telegram", "value": "other_hr"}],
        },
    )
    _conversations(ctx).record_outbound("anna_hr", "Уже писали")
    remote_calls = []

    class DialogClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def dialog_summaries(self, relevant_contacts):
            remote_calls.append(set(relevant_contacts))
            return [
                {
                    "contact": "other_hr",
                    "last_activity_at": "2026-10-01T10:00:00Z",
                    "last_message": {"direction": "in", "text": "Reply"},
                    "message_count": 1,
                    "unread": False,
                }
            ]

        def delete_dialog(self, contact):
            raise AssertionError(
                "Local removal must not delete Telegram dialog"
            )

    monkeypatch.setattr(api, "TelegramSourceClient", DialogClient)
    removed = client.delete("/api/telegram/contacts/anna_hr/local")
    assert removed.status_code == 200, removed.text
    assert removed.json()["removed"] == "anna_hr"
    assert _conversations(ctx).get("anna_hr") is None
    assert _conversations(ctx).already_contacted("anna_hr")
    assert _conversations(ctx).sent_today_count() == 1
    assert get_watch_post(ctx.output_folder, removed_post) is not None
    _conversations(ctx).record_inbound(
        "anna_hr", "Новый ответ", 99, datetime.now().astimezone()
    )
    save_watch_post(ctx.output_folder, POST)
    posts = client.get("/api/telegram/posts?scope=all").json()
    assert [post["id"] for post in posts["posts"]] == [kept_post]
    dialogs = client.get("/api/telegram/conversations").json()
    assert [row["contact"] for row in dialogs] == ["other_hr"]
    assert remote_calls == [{"other_hr"}]
    assert client.get("/api/telegram/conversations/anna_hr").status_code == 404
    assert not any(
        row.get("contact") == "anna_hr"
        for row in client.get("/api/inbox").json()
    )


def test_remove_contact_cleans_company_book_and_parser_cannot_readd(
    client,  # noqa: F811
):  # noqa: F811
    ctx = api.get_ctx()
    book = ContactBook(ctx.output_folder)
    book.add(
        "Acme",
        [
            {"kind": "telegram", "value": "anna_hr", "source": "telegram"},
            {"kind": "telegram", "value": "other_hr", "source": "telegram"},
            {"kind": "email", "value": "hr@acme.io", "source": "telegram"},
        ],
    )
    book.add(
        "",
        [{"kind": "telegram", "value": "anna_hr", "source": "telegram"}],
    )
    _post(ctx)
    response = client.delete("/api/telegram/contacts/anna_hr/local")
    assert response.status_code == 200, response.text
    assert [c["value"] for c in book.get("acme")["contacts"]] == [
        "other_hr",
        "hr@acme.io",
    ]
    assert book.get("@anna_hr") is None

    remember_telegram_post_contact(
        ctx.output_folder,
        POST["contacts"] + [{"kind": "email", "value": "hr@acme.io"}],
        {**POST, "company": "Acme"},
    )
    assert [c["value"] for c in book.get("acme")["contacts"]] == [
        "other_hr",
        "hr@acme.io",
    ]
    assert book.add("", POST["contacts"]) == ""
    assert book.add("Newco", POST["contacts"]) == ""
    assert book.get("newco") is None
    assert book.add("Manual", []) == "manual"
    assert book.get("manual") is not None


def test_remove_contact_present_only_in_company_book(client):  # noqa: F811
    ctx = api.get_ctx()
    book = ContactBook(ctx.output_folder)
    book.add(
        "Acme",
        [
            {"kind": "telegram", "value": "anna_hr", "source": "telegram"},
            {"kind": "email", "value": "hr@acme.io", "source": "telegram"},
        ],
    )

    removed = client.delete("/api/telegram/contacts/anna_hr/local")
    assert removed.status_code == 200, removed.text
    assert removed.json() == {"removed": "anna_hr"}
    assert [c["value"] for c in book.get("acme")["contacts"]] == ["hr@acme.io"]
    assert _conversations(ctx).is_dismissed("anna_hr")
    assert _conversations(ctx).already_contacted("anna_hr")


def test_remove_contact_does_not_match_email_with_same_value(
    client,  # noqa: F811
):  # noqa: F811
    ctx = api.get_ctx()
    book = ContactBook(ctx.output_folder)
    book.add(
        "Acme", [{"kind": "email", "value": "anna_hr", "source": "manual"}]
    )

    removed = client.delete("/api/telegram/contacts/anna_hr/local")
    assert removed.status_code == 404
    assert book.get("acme")["contacts"][0]["value"] == "anna_hr"
