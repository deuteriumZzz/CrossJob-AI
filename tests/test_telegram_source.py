from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from src.job_sources.telegram.source import TelegramSource


@dataclass
class _Message:
    id: int
    text: str
    date: datetime


class _Client:
    def __init__(self, messages):
        self.messages = messages

    def iter_channel_messages(self, channel, limit):
        return self.messages[:limit]


def test_telegram_source_keeps_only_last_seven_days_by_default():
    now = datetime.now(timezone.utc)
    source = TelegramSource(
        _Client(
            [
                _Message(1, "Python developer", now - timedelta(days=6)),
                _Message(2, "Python developer", now - timedelta(days=8)),
            ]
        )
    )

    jobs = source.search(
        {"positions": ["Python"], "telegram": {"channels": ["jobs"]}}
    )

    assert [job.external_id for job in jobs] == ["jobs_1"]


def test_telegram_source_respects_custom_age_window():
    now = datetime.now(timezone.utc)
    source = TelegramSource(
        _Client([_Message(3, "Python developer", now - timedelta(days=3))])
    )

    jobs = source.search(
        {
            "positions": ["Python"],
            "telegram": {"channels": ["jobs"], "max_post_age_days": 2},
        }
    )

    assert jobs == []


def test_telegram_source_uses_same_keywords_as_gateway():
    """Поле «Ключевые слова» (watch_keywords) действует и на поиск по
    расписанию, как на шлюз; пустое — значимые слова из должностей
    («Python разработчик» → «python»), а не вся фраза целиком."""
    now = datetime.now(timezone.utc)
    source = TelegramSource(
        _Client(
            [
                _Message(1, "Ищем Python-developer, удалённо", now),
                _Message(2, "Нужен Django инженер", now),
            ]
        )
    )
    prefs = {
        "positions": ["Python разработчик"],
        "telegram": {"channels": ["jobs"]},
    }
    assert [j.external_id for j in source.search(prefs)] == ["jobs_1"]
    prefs["telegram"]["watch_keywords"] = ["django"]
    assert [j.external_id for j in source.search(prefs)] == ["jobs_2"]
