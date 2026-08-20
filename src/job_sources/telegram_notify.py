import httpx

TELEGRAM_API_BASE = "https://api.telegram.org"


def send_notification(bot_token: str, chat_id: str, text: str) -> None:
    """Прямой httpx.post вместо Telethon (юзер-сессия, нужна для
    чтения каналов в TelegramSourceClient) — для простого "уведомить
    себя" достаточно обычного бота через @BotFather, без входа под
    личным аккаунтом."""
    response = httpx.post(
        f"{TELEGRAM_API_BASE}/bot{bot_token}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=10,
    )
    response.raise_for_status()
