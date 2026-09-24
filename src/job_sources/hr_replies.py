"""Реакция на ответы HR в личных диалогах Telegram: разбор ответа
(интерес / вопрос / отказ), черновики ответов и напоминаний на
подтверждение, утренняя сводка. Сами сообщения никогда не уходят без
подтверждения пользователя — см. main.check_telegram_replies."""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal, cast

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from src.job_sources.applied_log import AppliedLog, effective_stage
from src.job_sources.llm_provider import get_chat_llm
from src.utils.file_lock import state_file_lock

Category = Literal["interest", "question", "rejection", "other"]

CATEGORY_LABELS: dict[str, str] = {
    "interest": "🟢 интерес",
    "question": "🟡 вопрос",
    "rejection": "🔴 отказ",
    "other": "⚪ другое",
}
# Какой этап отклика означает ответ HR (None — этап не трогаем).
CATEGORY_STAGE: dict[str, str | None] = {
    "interest": "interview",
    "question": "replied",
    "rejection": "rejected",
    "other": None,
}

_CLASSIFY_PROMPT = ChatPromptTemplate.from_template(
    """
    Определи, что означает сообщение HR/работодателя кандидату в личной
    переписке по вакансии:
    - interest — зовут на интервью/созвон, просят прислать резюме или
      контакты, явно хотят продолжить;
    - question — задают вопрос, на который кандидату нужно ответить
      (зарплата, опыт, сроки выхода, формат работы…);
    - rejection — отказ, вакансия закрыта, "вы нам не подходите";
    - other — всё остальное (приветствие без сути, автоответ, спам).
    Если есть и приглашение, и вопрос — interest.

    Сообщение:
    {message_text}
    """
)


class _Classified(BaseModel):
    category: Category = Field(description="Тип ответа HR")


def classify_reply(message_text: str, llm_api_key: str) -> Category:
    llm = cast(BaseChatModel, get_chat_llm(llm_api_key, temperature=0))
    result = cast(
        _Classified,
        llm.with_structured_output(_Classified).invoke(
            _CLASSIFY_PROMPT.format(message_text=message_text)
        ),
    )
    return result.category


FOLLOW_UP_TEXT = (
    "Здравствуйте! Хотел уточнить, актуальна ли ещё вакансия — "
    "буду рад обсудить детали, если есть интерес."
)


class DraftStore:
    """Черновики сообщений HR, ждущие подтверждения: код из 4 символов →
    {contact, text, kind ("reply"|"follow_up"), job_link, created_at}.
    Подтверждают в дашборде ("Входящие") или командой в Telegram-боте
    "отправить <код>" / "пропустить <код>"."""

    def __init__(self, path: Path):
        self.path = path

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def add(
        self, contact: str, text: str, kind: str, job_link: str, **extra
    ) -> str:
        """extra — для писем: channel="email", subject, in_reply_to."""
        with state_file_lock(self.path):
            data = self._load()
            # Новый черновик тому же контакту заменяет старый — отвечать
            # надо на последнее сообщение, а не на все по очереди.
            data = {k: v for k, v in data.items() if v["contact"] != contact}
            code = secrets.token_hex(2)
            data[code] = {
                "contact": contact,
                "text": text,
                "kind": kind,
                "job_link": job_link,
                "created_at": datetime.now().astimezone().isoformat(),
                **extra,
            }
            self._save(data)
        return code

    def all(self) -> dict:
        return self._load()

    def get(self, code: str) -> dict | None:
        return self._load().get(code.lower())

    def update_text(self, code: str, text: str) -> bool:
        with state_file_lock(self.path):
            data = self._load()
            if code not in data:
                return False
            data[code]["text"] = text
            self._save(data)
        return True

    def remove(self, code: str) -> None:
        with state_file_lock(self.path):
            data = self._load()
            data.pop(code.lower(), None)
            self._save(data)


def due_follow_ups(
    conversations: list[dict], days: int, now: datetime | None = None
) -> list[dict]:
    """Диалоги, где мы писали, HR ни разу не ответил, последнему
    сообщению больше days дней и напоминания ещё не было."""
    if days <= 0:
        return []
    now = now or datetime.now().astimezone()
    due = []
    for conv in conversations:
        messages = conv.get("messages") or []
        if not messages or conv.get("followed_up"):
            continue
        if any(m["direction"] == "in" for m in messages):
            continue
        last_at = datetime.fromisoformat(messages[-1]["at"])
        if now - last_at >= timedelta(days=days):
            due.append(conv)
    return due


def format_draft_notification(
    contact: str, company_title: str, incoming: str, code: str, draft: str
) -> str:
    where = f" ({company_title})" if company_title else ""
    return (
        f"✈️ @{contact}{where}\n"
        f"HR: {incoming}\n\n"
        f"Черновик ответа:\n{draft}\n\n"
        f"«отправить {code}» — отправить, «пропустить {code}» — не "
        "отвечать. Или поправьте текст во «Входящих» в дашборде."
    )


def build_digest(
    applied_log: AppliedLog,
    conversations: list[dict],
    drafts: dict,
    now: datetime | None = None,
) -> str:
    """Утренняя сводка: что было за последние сутки и что ждёт вас."""
    now = now or datetime.now().astimezone()
    since = now - timedelta(days=1)
    entries = applied_log.find_by_company("")
    applied = sum(
        1
        for e in entries
        if e["status"] == "applied"
        and datetime.fromisoformat(e["applied_at"]) >= since
    )
    new_replies = [
        e
        for e in entries
        if effective_stage(e) is not None
        and e.get("state_at")
        and datetime.fromisoformat(e["state_at"]) >= since
    ]
    tg_replies = [
        c
        for c in conversations
        if any(
            m["direction"] == "in"
            and datetime.fromisoformat(m["at"]) >= since
            for m in c.get("messages") or []
        )
    ]
    interviews = [e for e in new_replies if effective_stage(e) == "interview"]
    lines = [
        "☀️ Сводка за сутки",
        f"Откликов: {applied}",
        f"Ответов: {len(new_replies) + len(tg_replies)}"
        + (f" (интервью: {len(interviews)})" if interviews else ""),
    ]
    for e in interviews[:5]:
        lines.append(f"🟢 {e['company']} — {e['title']}")
    if drafts:
        lines.append(f"Ждут вашего подтверждения: {len(drafts)} сообщ.")
    return "\n".join(lines)
