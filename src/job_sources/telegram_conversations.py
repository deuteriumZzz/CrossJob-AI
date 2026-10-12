from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from src.utils.file_lock import state_file_lock


def _counts_toward_limit(message: dict) -> bool:
    if message.get("counts_toward_limit") is False:
        return False
    # Older history stored a resume-file event as a plain outbound line.
    text = str(message.get("text") or "")
    return not text.startswith(
        ("Отправлено резюме (", "📎 Отправлено резюме (")
    )


def _preserve_sent_days(data: dict, conv: dict | None) -> None:
    if conv is None:
        return
    sent_days = dict(data.get("removed_sent_days", {}))
    for message in conv.get("messages", []):
        if message.get("direction") != "out":
            continue
        if not _counts_toward_limit(message):
            continue
        day = datetime.fromisoformat(message["at"]).date().isoformat()
        sent_days[day] = sent_days.get(day, 0) + 1
    data["removed_sent_days"] = sent_days


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
            self._data = {"conversations": [], "contacted": []}

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
        if self.is_dismissed(contact):
            return None
        return self._find(self._data, contact)

    def all(self) -> list[dict]:
        return sorted(
            [
                conv
                for conv in self._data["conversations"]
                if not self.is_dismissed(conv["contact"])
            ],
            key=lambda c: c["last_activity_at"],
            reverse=True,
        )

    def is_dismissed(self, contact: str) -> bool:
        return contact.lower().lstrip("@") in self._data.get(
            "dismissed_contacts", []
        )

    def record_outbound(
        self,
        contact: str,
        text: str,
        job_link: str = "",
        message_id: int | None = None,
        sent_at: datetime | None = None,
        counts_toward_limit: bool = True,
    ) -> None:
        now = (sent_at or datetime.now().astimezone()).isoformat()

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
                    **({"id": message_id} if message_id is not None else {}),
                    **(
                        {"counts_toward_limit": False}
                        if not counts_toward_limit
                        else {}
                    ),
                }
            )
            conv["last_activity_at"] = now
            data["contacted"] = sorted(
                set(data.get("contacted", [])) | {contact.lower()}
            )
            data["dismissed_contacts"] = [
                value
                for value in data.get("dismissed_contacts", [])
                if value != contact.lower().lstrip("@")
            ]

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

    def set_field(self, contact: str, key: str, value) -> None:
        """Служебные поля диалога: label (интерес/вопрос/отказ по
        последнему ответу HR), followed_up (напоминание уже было)."""

        def _mutate(data: dict) -> None:
            conv = self._find(data, contact)
            if conv is not None:
                conv[key] = value

        self._write_locked(_mutate)

    def already_contacted(self, contact: str) -> bool:
        return (
            self.is_dismissed(contact)
            or self._find(self._data, contact) is not None
            or contact.lower() in self._data.get("contacted", [])
        )

    def dismiss_local(self, contact: str) -> bool:
        """Hide a contact in this app without touching the Telegram dialog.

        Incoming sync may recreate a local message record; the tombstone
        keeps it out of the UI until an explicit outbound message is sent.
        The contacted ledger remains to prevent duplicate cold outreach.
        """
        normalized = contact.lower().lstrip("@")
        existed = self._find(self._data, contact) is not None

        def _mutate(data: dict) -> None:
            data["dismissed_contacts"] = sorted(
                set(data.get("dismissed_contacts", [])) | {normalized}
            )
            conv = self._find(data, contact)
            if conv is not None:
                data["contacted"] = sorted(
                    set(data.get("contacted", [])) | {normalized}
                )
                _preserve_sent_days(data, conv)
            data["conversations"] = [
                conv
                for conv in data["conversations"]
                if conv["contact"].lower().lstrip("@") != normalized
            ]

        self._write_locked(_mutate)
        return existed

    def mark_contacted(self, contacts: list[str]) -> None:
        """Учесть диалоги, найденные напрямую в Telegram, без копирования
        их сообщений в локальный журнал."""
        normalized = {contact.lower() for contact in contacts if contact}
        if not normalized or normalized.issubset(
            set(self._data.get("contacted", []))
        ):
            return

        def _mutate(data: dict) -> None:
            data["contacted"] = sorted(
                set(data.get("contacted", [])) | normalized
            )

        self._write_locked(_mutate)

    def delete(self, contact: str) -> bool:
        """Удаляет диалог целиком из истории (не архив — если контакт
        снова напишет или ему снова спишутся, диалог просто заведётся
        заново пустым). Возвращает False, если такого контакта и не
        было — чтобы вызывающий код мог отличить "удалили" от "нечего
        было удалять"."""
        existed = self.get(contact) is not None

        def _mutate(data: dict) -> None:
            if existed:
                data["contacted"] = sorted(
                    set(data.get("contacted", [])) | {contact.lower()}
                )
                _preserve_sent_days(data, self._find(data, contact))
            data["conversations"] = [
                c
                for c in data["conversations"]
                if c["contact"].lower() != contact.lower()
            ]

        self._write_locked(_mutate)
        return existed

    def sent_today_count(self) -> int:
        """Сколько исходящих сообщений реально отправлено сегодня —
        основа для дневного лимита холодных обращений (см.
        telegram.daily_message_limit), общего на все прогоны за день,
        а не только на этот запуск."""
        today = datetime.now().astimezone().date()
        return self._data.get("removed_sent_days", {}).get(
            today.isoformat(), 0
        ) + sum(
            1
            for conv in self._data["conversations"]
            for m in conv["messages"]
            if m["direction"] == "out"
            and _counts_toward_limit(m)
            and datetime.fromisoformat(m["at"]).date() == today
        )
