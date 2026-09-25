"""Реакция на ответы HR в личных диалогах Telegram: разбор ответа
(интерес / вопрос / отказ), черновики ответов и напоминаний на
подтверждение, утренняя сводка. Сами сообщения никогда не уходят без
подтверждения пользователя — см. main.check_telegram_replies."""

from __future__ import annotations

import json
import re
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal, cast

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from src.job_sources.applied_log import AppliedLog, effective_stage
from src.job_sources.llm_provider import get_chat_llm
from src.libs.resume_and_cover_builder.anti_ai_rules import ANTI_AI_STRUCTURE_RU, humanize
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


# Без тире и дежурных фраз — по правилам humanizer (anti_ai_rules.py).
FOLLOW_UP_TEXT = (
    "Здравствуйте! Хотел уточнить, актуальна ли ещё вакансия. "
    "Если да, с удовольствием созвонюсь и отвечу на вопросы."
)
FOLLOW_UP_TEXT_EN = (
    "Hello, I'm following up on my previous email. Is the role still open? "
    "If so, I'd be glad to have a short call."
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


# --- Первое сообщение HR (вкладка «Контакты») --------------------------

_FIRST_MESSAGE_PROMPT = ChatPromptTemplate.from_template(
    """
    Напиши первое сообщение кандидата рекрутеру по вакансии.
    Язык: {language}. Канал: {channel}.

    Правила:
    - Возьми из вакансии главные требования (сколько реально важно,
      обычно два-три) и на каждое дай конкретный пример из резюме, по
      возможности с цифрами.
    - Только факты из резюме — не придумывай опыт, цифры и факты о
      компании, которых нет в тексте вакансии.
    - Без клише ("внимательно изучив вашу вакансию", "с большим
      интересом", "I am writing to express my interest").
    - {length_rule}

    Кандидат: {candidate_name}
    Компания: {company}
    Вакансия: {job_title}
    Текст вакансии:
    {vacancy_text}

    Резюме:
    {resume_text}

    Верни только текст сообщения, без темы и подписи-шаблона.
    """
    # Правила «как человек» (humanizer) — и для русского, и для английского
    # текста: в них есть списки слов-маркеров на обоих языках.
    + ANTI_AI_STRUCTURE_RU
)

_LENGTH_RULES = {
    "telegram": "2–4 предложения, как в личном чате, без приветственной воды.",
    "email": (
        "150–180 слов: абзац «кто я и что ищу», абзац «почему именно эта "
        "компания» (только по тексту вакансии), 2–3 достижения, в конце — "
        "готов обсудить на звонке. Деловой тон."
    ),
}


def _looks_russian(text: str) -> bool:
    letters = [ch for ch in text if ch.isalpha()]
    cyrillic = sum(1 for ch in letters if "а" <= ch.lower() <= "я" or ch in "ёЁ")
    return bool(letters) and cyrillic / len(letters) > 0.3


# Домены России и СНГ, где деловая переписка обычно по-русски. Название
# компании у них часто латиницей (Ozon, Kaspi, EPAM) — по нему язык не понять.
_CIS_TLDS = ("ru", "su", "рф", "xn--p1ai", "by", "kz", "kg", "uz")


def _cis_company(card: dict) -> bool:
    hosts = [card.get("website") or ""] + [c["value"].split("@")[-1] for c in card.get("contacts", []) if c["kind"] == "email"]
    hosts = [h.lower().split("//")[-1].split("/")[0].rstrip(".") for h in hosts if h]
    return any(h.rsplit(".", 1)[-1] in _CIS_TLDS for h in hosts)


def generate_first_message(
    resume_pdf_path: Path,
    candidate_name: str,
    company: str,
    job_title: str,
    vacancy_text: str,
    channel: str,
    llm_api_key: str,
) -> dict:
    """{"subject", "text"} первого сообщения HR: channel — "telegram"
    или "email". Язык — как у вакансии (русская → по-русски)."""
    from langchain_core.output_parsers import StrOutputParser
    from pdfminer.high_level import extract_text

    russian = _looks_russian(vacancy_text or job_title)
    chain = (
        _FIRST_MESSAGE_PROMPT
        | get_chat_llm(llm_api_key, temperature=0.4)
        | StrOutputParser()
    )
    text = chain.invoke(
        {
            "language": "русский" if russian else "English",
            "channel": "Telegram" if channel == "telegram" else "email",
            "length_rule": _LENGTH_RULES[channel],
            "candidate_name": candidate_name or "кандидат",
            "company": company or "не указана",
            "job_title": job_title,
            "vacancy_text": (vacancy_text or "")[:6000],
            "resume_text": extract_text(str(resume_pdf_path)),
        }
    ).strip()
    text = humanize(text, llm_api_key)
    subject = f"{job_title} — {'отклик' if russian else 'Application'}"
    if candidate_name:
        subject += f" — {candidate_name}"
    return {"subject": subject, "text": text}


# --- Письмо компании из рассылки (вкладка «Контакты HR» → «Рассылка») -----

_COMPANY_EMAIL_PROMPT = ChatPromptTemplate.from_template(
    """
    Напиши короткое персонализированное сопроводительное письмо от имени
    кандидата. Язык: {language}.
    - Обращение по имени контакта ({contact_name}), если оно есть; иначе
      нейтральное приветствие.
    - Первый абзац: кто я и что ищу (позиция: {target_position}).
    - Второй абзац: почему именно эта компания — сошлись на сферу её
      деятельности или на вакансию, если она указана. Не выдумывай факты
      о компании, которых нет в данных ниже.
    - Третий абзац: два-три наиболее релевантных достижения из резюме,
      подобранных под профиль компании.
    - Завершение: готов обсудить на звонке, контакты.
    - Тон деловой и сжатый, без клише и без воды. Максимум 150–180 слов.

    Кандидат: {candidate_name}
    Компания: {company}
    Сайт: {website}
    Вакансия: {vacancy}
    На что сделать упор: {emphasis}

    Резюме:
    {resume_text}

    Верни только текст письма, без темы.
    """
    + ANTI_AI_STRUCTURE_RU
)


def generate_company_email(
    resume_pdf_path: Path,
    candidate_name: str,
    target_position: str,
    card: dict,
    contact_name: str,
    llm_api_key: str,
) -> dict:
    """{"subject", "text"} письма компании из базы контактов. Английский
    по умолчанию (как в промте), русский — если компания/упор по-русски."""
    from langchain_core.output_parsers import StrOutputParser
    from pdfminer.high_level import extract_text

    vacancy = (card.get("vacancies") or [{}])[-1]
    sample = " ".join([card.get("company", ""), card.get("emphasis", ""), vacancy.get("title", ""),
                       vacancy.get("text", "")[:1500]])
    russian = _looks_russian(sample) or _cis_company(card)
    chain = _COMPANY_EMAIL_PROMPT | get_chat_llm(llm_api_key, temperature=0.4) | StrOutputParser()
    text = chain.invoke(
        {
            "language": "русский" if russian else "English",
            "contact_name": contact_name or "не указано",
            "target_position": target_position,
            "candidate_name": candidate_name or "(имя — из резюме)",
            "company": card.get("company") or "не указана",
            "website": card.get("website") or "не указан",
            "vacancy": vacancy.get("title") or "не указана",
            "emphasis": card.get("emphasis") or "не указано",
            "resume_text": extract_text(str(resume_pdf_path)),
        }
    ).strip()
    # Модель иногда оставляет заготовки вида «[Your Name]» — не отправляем их.
    text = re.sub(r"\[(?:Your|Ваш[аеи]?)[^\]]*\]", candidate_name, text).strip()
    # Вторая проверка по скиллу humanizer: остались признаки — одна правка.
    text = humanize(text, llm_api_key)
    subject = (
        f"{target_position} — отклик — {candidate_name}" if russian
        else f"{target_position} Application — {candidate_name}"
    ).strip(" —")
    return {"subject": subject, "text": text}
