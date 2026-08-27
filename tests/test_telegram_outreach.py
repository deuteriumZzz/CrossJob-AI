"""Самопроверка для новой логики холодных сообщений в Telegram:
извлечение контакта из поста, нормализация ссылок на канал, окно
активных часов и хранилище истории переписки."""

from datetime import datetime

from src.job_sources.apply_pacing import within_active_hours
from src.job_sources.telegram.client import normalize_channel
from src.job_sources.telegram.contact import extract_contact
from src.job_sources.telegram_conversations import TelegramConversations


def test_extract_contact_single_mention():
    text = "Ищем Python-разработчика, пишите @hr_ivan в личку"
    assert extract_contact(text, channel="job_channel") == "hr_ivan"


def test_extract_contact_ignores_self_channel_mention():
    text = "Вакансия опубликована в @job_channel, контактов нет"
    assert extract_contact(text, channel="job_channel") is None


def test_extract_contact_ambiguous_returns_none():
    text = "Пишите @hr_ivan или @hr_maria"
    assert extract_contact(text, channel="job_channel") is None


def test_normalize_channel_accepts_links_and_usernames():
    assert normalize_channel("@some_channel") == "some_channel"
    assert normalize_channel("some_channel") == "some_channel"
    assert normalize_channel("https://t.me/some_channel") == "some_channel"
    assert normalize_channel("t.me/some_channel/123") == "some_channel"


def test_within_active_hours():
    now = datetime.now()
    assert within_active_hours(0, 24) is True
    assert within_active_hours(now.hour, now.hour + 1) is True
    outside_hour = (now.hour + 2) % 24
    assert within_active_hours(outside_hour, outside_hour) is False


def test_telegram_conversations_roundtrip(tmp_path):
    store = TelegramConversations(tmp_path / "telegram_conversations.json")

    assert store.already_contacted("hr_ivan") is False
    store.record_outbound(
        "hr_ivan", "Здравствуйте!", job_link="https://t.me/x/1"
    )
    assert store.already_contacted("hr_ivan") is True
    assert store.sent_today_count() == 1

    conv = store.get("hr_ivan")
    assert conv["unread"] is False

    store.record_inbound(
        "hr_ivan", "Здравствуйте, расскажите о себе", 42, datetime.now()
    )
    conv = store.get("hr_ivan")
    assert conv["unread"] is True
    assert conv["last_incoming_id"] == 42
    assert len(conv["messages"]) == 2

    store.mark_read("hr_ivan")
    assert store.get("hr_ivan")["unread"] is False


if __name__ == "__main__":
    test_extract_contact_single_mention()
    test_extract_contact_ignores_self_channel_mention()
    test_extract_contact_ambiguous_returns_none()
    test_normalize_channel_accepts_links_and_usernames()
    test_within_active_hours()
    print("OK")
