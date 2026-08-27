from datetime import datetime, timedelta, timezone

from src.job import Job
from src.job_sources.telegram.client import (
    TelegramSourceClient,
    normalize_channel,
)
from src.job_sources.telegram.mapping import telegram_message_to_job
from src.job_sources.preferences import effective_list

# ponytail: фиксированное число сообщений на канал вместо обхода всей
# истории, увеличить, если это перестанет давать достаточно постов.
MESSAGES_PER_CHANNEL_DEFAULT = 100

# Без ограничения по свежести messages_per_channel листает вглубь
# истории канала с редкими постами и легко доносит до пользователя
# вакансию месячной давности — писать по такой автору уже поздно
# (закрыта). limit по количеству сообщений остаётся (не листать канал
# целиком), но каждый пост дополнительно проверяется по дате.
MAX_POST_AGE_DAYS_DEFAULT = 7


def _matches_any(text_lower: str, terms: list) -> bool:
    return any(term.lower() in text_lower for term in terms)


def _passes_telegram_filters(text: str, preferences: dict) -> bool:
    """У постов нет структурированных полей company/title/location,
    поэтому чёрные списки и разрешённые локации сверяются со всем
    текстом сообщения целиком, а не по отдельным полям (в отличие от
    passes_blacklists)."""
    text_lower = text.lower()

    if _matches_any(text_lower, preferences.get("company_blacklist", [])):
        return False
    if _matches_any(text_lower, preferences.get("title_blacklist", [])):
        return False
    if _matches_any(text_lower, preferences.get("location_blacklist", [])):
        return False

    locations = effective_list(preferences, "telegram", "locations")
    if locations and not _matches_any(text_lower, locations):
        return False

    return True


class TelegramSource:
    def __init__(self, client: TelegramSourceClient):
        self.client = client

    def search(self, preferences: dict) -> list[Job]:
        keywords = effective_list(preferences, "telegram", "positions")
        telegram_preferences = preferences.get("telegram") or {}
        channels = [
            normalize_channel(c)
            for c in telegram_preferences.get("channels", [])
        ]
        limit = telegram_preferences.get(
            "messages_per_channel", MESSAGES_PER_CHANNEL_DEFAULT
        )
        max_age_days = telegram_preferences.get(
            "max_post_age_days", MAX_POST_AGE_DAYS_DEFAULT
        )
        oldest_allowed = datetime.now(timezone.utc) - timedelta(
            days=max_age_days
        )

        jobs: list[Job] = []
        for channel in channels:
            for message in self.client.iter_channel_messages(
                channel, limit=limit
            ):
                if message.date and message.date < oldest_allowed:
                    continue
                text = (message.text or "").strip()
                if not text:
                    continue
                text_lower = text.lower()
                if keywords and not _matches_any(text_lower, keywords):
                    continue
                if not _passes_telegram_filters(text, preferences):
                    continue

                jobs.append(telegram_message_to_job(channel, message))

        return jobs
