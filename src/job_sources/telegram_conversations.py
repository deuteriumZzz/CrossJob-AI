from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from src.utils.file_lock import state_file_lock


class TelegramConversations:
    """История переписки с контактами из постов в Telegram-каналах —
    отдельно от applied_log.py (тот ведёт учёт по вакансиям на
    площадках, здесь же диалог идёт с человеком и может касаться
    нескольких постов подряд). По образцу AppliedLog: JSON-файл под
    блокировкой, чтобы демон (проверка новых ответов) и вебui (ручная
    отправка из чата) не затирали правки друг друга."""

    def __init__(self, path: Path):
        self.path = path
        if self.path.exists():
            self._data = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self._data = {"conversations": []}

    def _write_locked(self, mutate) -> None:
        with state_file_lock(self.path):
            fresh = (
                json.loads(self.path.read_text(encoding="utf-8"))
                if self.path.exists()
                else {"conversations": []}
            )
            mutate(fresh)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(fresh, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        self._data = fresh

    def _find(self, data: dict, contact: str) -> dict | None:
        for conv in data["conversations"]:
            if conv["contact"].lower() == contact.lower():
                return conv
        return None

    def get(self, contact: str) -> dict | None:
        return self._find(self._data, contact)

    def all(self) -> list[dict]:
        return sorted(
            self._data["conversations"],
            key=lambda c: c["last_activity_at"],
            reverse=True,
        )

    def record_outbound(
        self, contact: str, text: str, job_link: str = ""
    ) -> None:
        now = datetime.now().astimezone().isoformat()

        def _mutate(data: dict) -> None:
            conv = self._find(data, contact)
            if conv is None:
                conv = {
                    "contact": contact,
                    "messages": [],
                    "last_incoming_id": 0,
                    "last_activity_at": now,
                    "unread": False,
                }
                data["conversations"].append(conv)
            conv["messages"].append(
                {
                    "direction": "out",
                    "text": text,
                    "at": now,
                    "job_link": job_link,
                }
            )
            conv["last_activity_at"] = now

        self._write_locked(_mutate)

    def record_inbound(
        self, contact: str, text: str, message_id: int, at: datetime
    ) -> None:
        def _mutate(data: dict) -> None:
            conv = self._find(data, contact)
            if conv is None:
                conv = {
                    "contact": contact,
                    "messages": [],
                    "last_incoming_id": 0,
                    "last_activity_at": at.isoformat(),
                    "unread": False,
                }
                data["conversations"].append(conv)
            conv["messages"].append(
                {"direction": "in", "text": text, "at": at.isoformat()}
            )
            conv["last_incoming_id"] = max(
                conv.get("last_incoming_id", 0), message_id
            )
            conv["last_activity_at"] = at.isoformat()
            conv["unread"] = True

        self._write_locked(_mutate)

    def mark_read(self, contact: str) -> None:
        """Открыли диалог в UI — гасит бейдж "N непрочитанных"."""

        def _mutate(data: dict) -> None:
            conv = self._find(data, contact)
            if conv is not None:
                conv["unread"] = False

        self._write_locked(_mutate)

    def already_contacted(self, contact: str) -> bool:
        return self.get(contact) is not None

    def sent_today_count(self) -> int:
        """Сколько исходящих сообщений реально отправлено сегодня —
        основа для дневного лимита холодных обращений (см.
        telegram.daily_message_limit), общего на все прогоны за день,
        а не только на этот запуск."""
        today = datetime.now().astimezone().date()
        return sum(
            1
            for conv in self._data["conversations"]
            for m in conv["messages"]
            if m["direction"] == "out"
            and datetime.fromisoformat(m["at"]).date() == today
        )
