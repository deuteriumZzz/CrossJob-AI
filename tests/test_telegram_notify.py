import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.job_sources.telegram_notify import (
    TelegramAPIError,
    get_or_create_topic,
    notify_manual_login_required,
    raise_for_telegram_status,
    send_notification,
)


def test_notify_manual_login_required_mentions_source_and_timeout():
    parameters = {"secretsFile": "unused"}
    with patch(
        "src.job_sources.telegram_notify.notify_from_secrets"
    ) as mock_notify:
        notify_manual_login_required(parameters, "hh.ru", 300)

    mock_notify.assert_called_once()
    called_parameters, called_text = mock_notify.call_args[0]
    assert called_parameters is parameters
    assert "hh.ru" in called_text
    assert "300" in called_text


def test_send_notification_posts_to_telegram_api():
    mock_response = MagicMock()
    with patch("httpx.post", return_value=mock_response) as mock_post:
        send_notification("BOT_TOKEN", "12345", "hello")

    mock_post.assert_called_once_with(
        "https://api.telegram.org/botBOT_TOKEN/sendMessage",
        json={"chat_id": "12345", "text": "hello"},
        timeout=10,
    )
    mock_response.raise_for_status.assert_called_once()


def test_telegram_http_error_never_exposes_bot_token():
    response = MagicMock()
    response.raise_for_status.side_effect = RuntimeError(
        "request failed: https://api.telegram.org/botSUPER_SECRET/getUpdates"
    )
    response.status_code = 409
    response.json.return_value = {"description": "Conflict"}

    try:
        raise_for_telegram_status(response, "getUpdates")
    except TelegramAPIError as error:
        assert "SUPER_SECRET" not in str(error)
        assert "409" in str(error) and "Conflict" in str(error)
    else:
        raise AssertionError("TelegramAPIError was not raised")


def _params_with_secrets(tmp_path: Path) -> dict:
    secrets_file = tmp_path / "secrets.yaml"
    secrets_file.write_text(
        "notifications:\n"
        "  telegram_bot_token: BOT_TOKEN\n"
        "  telegram_chat_id: -100123\n"
    )
    return {"secretsFile": secrets_file, "outputFileDirectory": tmp_path}


def test_get_or_create_topic_creates_and_caches():
    with tempfile.TemporaryDirectory() as tmp:
        parameters = _params_with_secrets(Path(tmp))
        with patch(
            "src.job_sources.telegram_notify.bot_request",
            return_value={"message_thread_id": 42},
        ) as mock_request:
            thread_id = get_or_create_topic(parameters, "avito")
            assert thread_id == 42
            # Второй вызов — из кэша, без повторного createForumTopic.
            thread_id_again = get_or_create_topic(parameters, "avito")
            assert thread_id_again == 42
            mock_request.assert_called_once()

        cache = json.loads((Path(tmp) / ".telegram_topics.json").read_text())
        assert cache == {"avito": 42}


def test_get_or_create_topic_falls_back_to_none_on_plain_chat():
    """Обычный личный чат с ботом (не супергруппа с темами) —
    createForumTopic вернёт ошибку, get_or_create_topic не должен
    падать, просто отдаёт None (вызывающий код шлёт без темы)."""
    with tempfile.TemporaryDirectory() as tmp:
        parameters = _params_with_secrets(Path(tmp))
        with patch(
            "src.job_sources.telegram_notify.bot_request",
            side_effect=TelegramAPIError("Bad Request: chat is not a forum"),
        ):
            thread_id = get_or_create_topic(parameters, "avito")
        assert thread_id is None


def test_get_or_create_topic_without_credentials_returns_none():
    with tempfile.TemporaryDirectory() as tmp:
        parameters = {
            "secretsFile": Path(tmp) / "missing.yaml",
            "outputFileDirectory": Path(tmp),
        }
        assert get_or_create_topic(parameters, "avito") is None


if __name__ == "__main__":
    test_send_notification_posts_to_telegram_api()
    print("All tests passed.")
