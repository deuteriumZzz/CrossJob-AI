"""Интервью в календарь без входа в Google: файл .ics (RFC 5545), который
открывается одним нажатием в любом календаре (Google, Apple, Outlook).
Дату и время из сообщения HR достаёт LLM ("завтра в 15:00" → точное
время) — если времени в сообщении нет, файл не создаётся."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, cast

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from src.job_sources.llm_provider import get_chat_llm

_EXTRACT_PROMPT = ChatPromptTemplate.from_template(
    """
    Сейчас {now} (часовой пояс кандидата {tz}). В сообщении HR есть
    конкретные дата и время интервью/созвона? Если да — верни их в
    формате ISO 8601 с часовым поясом (если пояс не указан — пояс
    кандидата). Если время не названо точно ("на следующей неделе",
    "в удобное время") — верни пустую строку.

    Сообщение:
    {message_text}
    """
)


class _When(BaseModel):
    start: str = Field(description="ISO 8601 с часовым поясом или пустая строка")


def extract_interview_time(
    message_text: str, llm_api_key: str, now: Optional[datetime] = None
) -> Optional[datetime]:
    now = now or datetime.now().astimezone()
    llm = cast(BaseChatModel, get_chat_llm(llm_api_key, temperature=0))
    result = cast(
        _When,
        llm.with_structured_output(_When).invoke(
            _EXTRACT_PROMPT.format(
                now=now.isoformat(timespec="minutes"),
                tz=now.strftime("%z"),
                message_text=message_text,
            )
        ),
    )
    try:
        start = datetime.fromisoformat(result.start.strip())
    except ValueError:
        return None
    return start if start.tzinfo else start.replace(tzinfo=now.tzinfo)


def _escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def build_ics(
    start: datetime,
    title: str,
    description: str = "",
    url: str = "",
    duration_minutes: int = 60,
) -> str:
    def fmt(moment: datetime) -> str:
        return moment.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//CrossJob-AI//interview//RU",
        "BEGIN:VEVENT",
        f"UID:{secrets.token_hex(8)}@crossjob-ai",
        f"DTSTAMP:{fmt(datetime.now(timezone.utc))}",
        f"DTSTART:{fmt(start)}",
        f"DTEND:{fmt(start + timedelta(minutes=duration_minutes))}",
        f"SUMMARY:{_escape(title)}",
        f"DESCRIPTION:{_escape(description)}",
    ]
    if url:
        lines.append(f"URL:{url}")
    lines += [
        "BEGIN:VALARM",
        "TRIGGER:-PT30M",
        "ACTION:DISPLAY",
        f"DESCRIPTION:{_escape(title)}",
        "END:VALARM",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(lines) + "\r\n"
