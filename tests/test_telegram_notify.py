from unittest.mock import MagicMock, patch

from src.job_sources.telegram_notify import send_notification


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


if __name__ == "__main__":
    test_send_notification_posts_to_telegram_api()
    print("All tests passed.")
