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

from src.job_sources.applied_log import AppliedLog, Stage, effective_stage
from src.job_sources.html_text import html_letter_to_plain_text
from src.job_sources.llm_provider import get_chat_llm
from src.libs.resume_and_cover_builder.anti_ai_rules import (
    ANTI_AI_STRUCTURE_RU,
    humanize,
)
from src.utils.file_lock import state_file_lock

Category = Literal["interest", "question", "rejection", "other"]

CATEGORY_LABELS: dict[str, str] = {
    "interest": "🟢 интерес",
    "question": "🟡 вопрос",
    "rejection": "🔴 отказ",
    "other": "⚪ другое",
}
# Какой этап отклика означает ответ HR (None — этап не трогаем).
CATEGORY_STAGE: dict[str, Stage | None] = {
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


_OPT_OUT_PROMPT = ChatPromptTemplate.from_template(
    """
    Ответ на холодное письмо кандидата компании — просят ли здесь
    больше не писать/не присылать письма/убрать из рассылки (в любой
    форме, включая "это письмо не по адресу", "ошиблись адресатом",
    "не занимаемся наймом", жёсткое "перестаньте спамить")? Обычный
    отказ по вакансии ("сейчас нет позиций", "не подходите") — НЕ
    просьба прекратить писать, это true только для явного требования
    остановить переписку насовсем.

    Сообщение:
    {message_text}
    """
)


class _OptOut(BaseModel):
    stop_contact: bool = Field(
        description="Просят прекратить присылать письма"
    )


def looks_like_opt_out(message_text: str, llm_api_key: str) -> bool:
    """True — ответ на холодное письмо компании просит больше не
    писать. Отдельная (не classify_reply) бинарная проверка: та
    классифицирует ответ HR по уже идущей вакансии на 4 категории,
    здесь же нужен только один явный сигнал для базы компаний —
    смешивать их в одну функцию усложнило бы обе."""
    llm = cast(BaseChatModel, get_chat_llm(llm_api_key, temperature=0))
    result = cast(
        _OptOut,
        llm.with_structured_output(_OptOut).invoke(
            _OPT_OUT_PROMPT.format(message_text=message_text)
        ),
    )
    return result.stop_contact


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


def due_hh_reminders(
    entries: list[dict], days: int, now: datetime | None = None
) -> list[dict]:
    """Отклики HH, которые никто не просмотрел (или без сохранённого
    статуса вовсе) дольше days дней, — кандидаты на напоминание в чате.
    Уже напомненные (reminder_sent_at) не повторяются — одно
    напоминание на отклик, не спам."""
    if days <= 0:
        return []
    now = now or datetime.now().astimezone()
    due = []
    for entry in entries:
        if entry.get("reminder_sent_at"):
            continue
        state = entry.get("last_known_state")
        if state not in (None, "", "Не просмотрен"):
            continue  # уже посмотрели/ответили/отказали — не молчание
        applied_at = entry.get("applied_at")
        if not applied_at:
            continue
        if now - datetime.fromisoformat(applied_at) >= timedelta(days=days):
            due.append(entry)
    return due


def hh_reminder_text(entry: dict) -> str:
    """Короткое, нейтральное — не выглядит навязчивым."""
    title = entry.get("title") or "вакансия"
    if _looks_russian(title):
        return (
            f"Здравствуйте! Напоминаю о своём отклике на «{title}» — если "
            "позиция ещё актуальна, буду рад пообщаться."
        )
    return (
        f"Hello! Just following up on my application for {title} — happy "
        "to chat if the role is still open."
    )


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
            m["direction"] == "in" and datetime.fromisoformat(m["at"]) >= since
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
    - Если в тексте вакансии указано имя контактного лица (например
      "писать Имя", "контакт: Имя", "@username (Имя)") — начни с
      обращения по этому имени. Время суток сейчас: {time_of_day} —
      если оно не пустое, используй его в приветствии ("Имя, {time_of_day}"
      на русском; на английском просто "Hi Имя,", без аналога времени
      суток). Если {time_of_day} пустое (поздняя ночь) — обратись по
      имени без временной фразы ("Имя, "). Если имени нигде нет —
      начинай сразу по делу, без "Здравствуйте"/"Hello" и без разгона
      перед мыслью — это деловое сообщение, а не письмо незнакомцу с
      нуля.
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
    "telegram": (
        "СТРОГО не больше 450-500 символов считая пробелы — это личное "
        "сообщение в чате, а не письмо, но и не голая строка: живой "
        "человек в первом сообщении рекрутёру обычно даёт 2 конкретных "
        "факта о себе, а не один. Структура: одно предложение, какая "
        "вакансия заинтересовала; дальше 2 конкретных факта из резюме "
        "с цифрами (стек, масштаб, результат — не общие слова вроде "
        "'опытный разработчик'); в конце — короткий вопрос про "
        "актуальность позиции. Резюме прикладывается отдельным файлом "
        "ботом — ссылку на него в текст не добавляй. Никакого "
        "приветствия-разгона ('Здравствуйте! Меня заинтересовала ваша "
        "вакансия...') — сразу по сути. Без ссылок, списков и эмодзи."
    ),
    "email": (
        "150–180 слов: абзац «кто я и что ищу», абзац «почему именно эта "
        "компания» (только по тексту вакансии), 2–3 достижения, в конце — "
        "готов обсудить на звонке. Деловой тон."
    ),
}


def greeting_time_phrase(now: datetime | None = None) -> str:
    """Приветствие по времени суток в Москве (стандарт делового
    времени для СНГ-рынка, вне зависимости от того, где физически
    находится сервер) — вместо зашитого "добрый день", когда письмо
    может уйти и утром, и вечером. Пусто поздней ночью (0-6ч) — там
    неуместно и "доброй ночи", и "доброе утро"."""
    from zoneinfo import ZoneInfo

    moment = (now or datetime.now(ZoneInfo("Europe/Moscow"))).astimezone(
        ZoneInfo("Europe/Moscow")
    )
    hour = moment.hour
    if 6 <= hour < 12:
        return "доброе утро"
    if 12 <= hour < 18:
        return "добрый день"
    if 18 <= hour < 23:
        return "добрый вечер"
    return ""


def _looks_russian(text: str) -> bool:
    letters = [ch for ch in text if ch.isalpha()]
    cyrillic = sum(
        1 for ch in letters if "а" <= ch.lower() <= "я" or ch in "ёЁ"
    )
    return bool(letters) and cyrillic / len(letters) > 0.3


# Домены России и СНГ, где деловая переписка обычно по-русски. Название
# компании у них часто латиницей (Ozon, Kaspi, EPAM) — по нему язык не понять.
_CIS_TLDS = ("ru", "su", "рф", "xn--p1ai", "by", "kz", "kg", "uz")


def _cis_company(card: dict) -> bool:
    hosts = [card.get("website") or ""] + [
        c["value"].split("@")[-1]
        for c in card.get("contacts", [])
        if c["kind"] == "email"
    ]
    hosts = [
        h.lower().split("//")[-1].split("/")[0].rstrip(".") for h in hosts if h
    ]
    return any(h.rsplit(".", 1)[-1] in _CIS_TLDS for h in hosts)


def company_uses_russian(card: dict) -> bool:
    """Use the same language decision for a campaign letter and its CV."""
    vacancy = (card.get("vacancies") or [{}])[-1]
    sample = " ".join(
        [
            card.get("company", ""),
            card.get("emphasis", ""),
            vacancy.get("title", ""),
            vacancy.get("text", "")[:1500],
        ]
    )
    return _looks_russian(sample) or _cis_company(card)


_TELEGRAM_MESSAGE_LIMIT = 500


def _fit_telegram_length(text: str) -> str:
    """LLM не всегда точно держит символьный лимит из промта (как и с
    остальными правилами длины в проекте) — обрезаем по границе
    предложения, а не как попало, если модель написала длиннее."""
    if len(text) <= _TELEGRAM_MESSAGE_LIMIT:
        return text
    head = text[:_TELEGRAM_MESSAGE_LIMIT]
    for stop in (". ", "! ", "? ", "\n"):
        cut = head.rfind(stop)
        if cut > _TELEGRAM_MESSAGE_LIMIT * 0.5:
            return head[: cut + 1].strip()
    cut = head.rfind(" ")
    return (head[:cut] if cut > 0 else head).strip()


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
            "time_of_day": greeting_time_phrase() if russian else "",
        }
    ).strip()
    text = humanize(text, llm_api_key)
    if channel == "telegram":
        text = _fit_telegram_length(text)
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
      нейтральное обращение к команде найма компании (например "Dear
      {company} Talent Team" на английском, "Здравствуйте" на русском) —
      не пиши безликое "Dear Hiring Team" без названия компании.
    - Первый абзац: кто я и что ищу (позиция: {target_position}), и одна
      фраза, почему именно эта компания — сошлись на сферу её
      деятельности или на вакансию, если она указана. Не выдумывай факты
      о компании, которых нет в данных ниже.
    - Дальше — список из 2-3 пунктов (каждый с "* " в начале строки):
      самые релевантные достижения из резюме под профиль компании, с
      цифрами и масштабом, а не общими словами. Это единственное
      исключение из общего правила "без списков с метками" ниже — только
      для этого блока.
    - Завершение: одна фраза, что готов обсудить на звонке. Про контакты
      и подпись ничего не пиши — это добавится отдельно после письма,
      не смешивай.
    - Подпись НЕ пиши вообще — ни имени, ни "С уважением"/"Best regards".
      Заканчивай текст на завершающей фразе про звонок.
    - Тон деловой и сжатый, без клише и без воды. Максимум 150–180 слов.
    - Также верни поле role_in_letter_language: точная позиция
      "{target_position}", переведённая на язык письма ({language}), если
      она изначально на другом языке — не меняй смысл, только язык.
      Если она уже на языке {language} — верни её как есть.

    Кандидат: {candidate_name}
    Компания: {company}
    Сайт: {website}
    Вакансия: {vacancy}
    На что сделать упор: {emphasis}

    Резюме:
    {resume_text}
    """
    + ANTI_AI_STRUCTURE_RU
)


class _CompanyEmail(BaseModel):
    letter: str = Field(description="Текст письма, без темы и подписи")
    role_in_letter_language: str = Field(
        description="Название должности на языке письма"
    )


def _personal_info_from_resume(parameters: dict) -> dict:
    """personal_information из plain_text_resume.yaml — тот же файл, что
    уже используют prefill_direct_application и генерация PDF-резюме.
    Ничего не парсит заново: просто читает то, что там уже разложено."""
    import yaml
    from src.utils.constants import PLAIN_TEXT_RESUME_YAML

    resume_yaml = parameters.get("plainTextResumeFile") or (
        parameters["dataFolder"] / PLAIN_TEXT_RESUME_YAML
    )
    try:
        data = yaml.safe_load(Path(resume_yaml).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    personal = (data or {}).get("personal_information") or {}
    # Незаполненные поля шаблона резюме остаются как "[Your Phone
    # Number]"/"[Your GitHub Profile URL]" — заметил в реальном
    # отправленном письме, что такой плейсхолдер сам утёк в подпись.
    # Значение целиком в квадратных скобках — не настоящий ответ.
    return {
        k: v
        for k, v in personal.items()
        if not (isinstance(v, str) and v.strip().startswith("[") and v.strip().endswith("]"))
    }


def _candidate_own_contacts(parameters: dict) -> list[str]:
    """Email и телефон кандидата, известные заранее — сырые значения
    для _strip_model_signoff (не готовая строка для письма, этим
    занимается build_contact_footer)."""
    import yaml

    try:
        secrets_data = (
            yaml.safe_load(
                Path(parameters["secretsFile"]).read_text(encoding="utf-8")
            )
            or {}
        )
    except (OSError, ValueError):
        secrets_data = {}
    direct = parameters.get("direct") or {}
    personal = _personal_info_from_resume(parameters)
    email = (secrets_data.get("email") or {}).get("address") or ""
    phone = direct.get("candidate_whatsapp") or "".join(
        filter(
            None, [personal.get("phone_prefix", ""), personal.get("phone", "")]
        )
    )
    return [c for c in (email, phone) if c]


def _strip_model_signoff(text: str, contacts: list[str]) -> str:
    """Промпт прямо просит не писать подпись и контакты в письме — но
    слабые (бесплатные) модели это правило иногда всё же нарушают и
    дописывают "Best regards, Имя, email, телефон" в конце, задваивая
    наш собственный footer (см. build_contact_footer). Контакты
    кандидата известны заранее, так что если модель их всё-таки
    вписала — это и есть начало самодеятельной подписи, обрезаем
    текст с начала этого абзаца."""
    cut_at = min(
        (text.find(c) for c in contacts if c and c in text), default=-1
    )
    if cut_at == -1:
        return text.strip()
    para_start = text.rfind("\n\n", 0, cut_at)
    return text[: para_start if para_start != -1 else cut_at].strip()


def build_contact_footer(parameters: dict, resume_pdf_path: Path) -> str:
    """Строка контактов в конце письма — собирается кодом, не моделью,
    чтобы не придумывала лишнего. Источник по умолчанию — уже
    разобранное резюме (plain_text_resume.yaml + сам текст PDF на
    Telegram); поля в Настройках → Почта и письма ("Мои контакты для
    подписи писем") — только override/фолбэк, если в резюме этого нет.
    Если контакта нет нигде — просто не добавляется, ничего не выдумываем."""
    import yaml
    from pdfminer.high_level import extract_text as _extract_text

    from src.job_sources.contact_book import contacts_from_text

    try:
        secrets_data = (
            yaml.safe_load(
                Path(parameters["secretsFile"]).read_text(encoding="utf-8")
            )
            or {}
        )
    except (OSError, ValueError):
        secrets_data = {}
    direct = parameters.get("direct") or {}
    personal = _personal_info_from_resume(parameters)

    # Первая строка: голые email/телефон, без подписей — самоочевидны.
    # Вторая: соцсети/код с подписью-лейблом ("Telegram: ", "GitHub: ",
    # "LinkedIn: "), потому что сама ссылка не всегда говорит, что это.
    line1: list[str] = []
    email = (secrets_data.get("email") or {}).get("address") or ""
    if email:
        line1.append(email)

    whatsapp = direct.get("candidate_whatsapp") or "".join(
        filter(None, [personal.get("phone_prefix", ""), personal.get("phone", "")])
    )
    if whatsapp:
        line1.append(whatsapp)

    line2: list[str] = []
    telegram = direct.get("candidate_telegram") or ""
    if not telegram:
        try:
            found = contacts_from_text(_extract_text(str(resume_pdf_path)))
            telegram = next(
                (c["value"] for c in found if c["kind"] == "telegram"), ""
            )
        except Exception:
            telegram = ""
    if telegram:
        handle = telegram.strip()
        if "t.me/" in handle:
            handle = handle.rsplit("t.me/", 1)[-1]
        elif handle.startswith("http"):
            handle = handle.rsplit("/", 1)[-1]
        handle = handle.lstrip("@").strip("/")
        if handle:
            line2.append(f"Telegram: @{handle}")

    github_user = (secrets_data.get("github") or {}).get(
        "username"
    ) or personal.get("github", "")
    if github_user:
        github_display = (
            github_user
            if github_user.startswith("http")
            else f"github.com/{github_user.lstrip('@')}"
        )
        line2.append(f"GitHub: {github_display}")

    linkedin = direct.get("candidate_linkedin") or personal.get("linkedin", "")
    if linkedin:
        line2.append(f"LinkedIn: {linkedin}")

    return "\n".join(
        " | ".join(line) for line in (line1, line2) if line
    )


def generate_company_email(
    resume_pdf_path: Path,
    candidate_name: str,
    target_position: str,
    card: dict,
    contact_name: str,
    llm_api_key: str,
    parameters: dict,
) -> dict:
    """{"subject", "text"} письма компании из базы контактов. Английский
    по умолчанию (как в промте), русский — если компания/упор по-русски."""
    from pdfminer.high_level import extract_text

    vacancy = (card.get("vacancies") or [{}])[-1]
    russian = company_uses_russian(card)
    language = "русский" if russian else "English"
    llm = cast(BaseChatModel, get_chat_llm(llm_api_key, temperature=0.4))
    chain = _COMPANY_EMAIL_PROMPT | llm.with_structured_output(_CompanyEmail)
    result = cast(
        _CompanyEmail,
        chain.invoke(
            {
                "language": language,
                "contact_name": contact_name or "не указано",
                "target_position": target_position,
                "candidate_name": candidate_name or "(имя — из резюме)",
                "company": card.get("company") or "не указана",
                "website": card.get("website") or "не указан",
                "vacancy": vacancy.get("title") or "не указана",
                "emphasis": card.get("emphasis") or "не указано",
                "resume_text": extract_text(str(resume_pdf_path)),
            }
        ),
    )
    # Модель иногда возвращает <br>/другие теги вместо переносов строк
    # (подтверждено на реальном отправленном письме — Gmail шлёт это
    # как обычный текст, теги видны получателю буквально). Тот же
    # чистильщик, что уже используется для cover letter на GetMatch/hh.
    text = html_letter_to_plain_text(result.letter)
    # Модель иногда оставляет заготовки вида «[Your Name]» — не отправляем их.
    text = re.sub(
        r"\[(?:Your|Ваш[аеи]?)[^\]]*\]", candidate_name, text
    ).strip()
    # Промпт прямо просит не писать подпись/контакты, но модель это
    # иногда игнорирует ("Best regards, Имя, email, телефон") — обрезаем
    # раньше humanize(), чтобы та не тратилась на переписывание блока,
    # который всё равно будет отброшен.
    text = _strip_model_signoff(text, _candidate_own_contacts(parameters))
    # Вторая проверка по скиллу humanizer: остались признаки — одна правка.
    text = humanize(text, llm_api_key)
    footer = build_contact_footer(parameters, resume_pdf_path)
    # Холодное письмо тысячам компаний — без явной опции "не писать
    # больше" получатель может только молча пожаловаться на спам (бьёт
    # по репутации ящика, см. "Защита почты от блокировки") вместо
    # простого ответа. Одна строка, не блок текста — не должна выглядеть
    # как рассылка с юридической плашкой.
    opt_out = (
        "\n\nЕсли это письмо не по адресу или вы не хотите получать "
        "такие письма — просто ответьте, и я больше не буду писать."
        if russian
        else "\n\nIf this isn't relevant or you'd rather not hear from "
        "me again, just reply and I won't follow up."
    )
    if footer:
        text = f"{text}\n\n{candidate_name}\n{footer}{opt_out}"
    else:
        text = f"{text}\n\n{candidate_name}{opt_out}"
    role = result.role_in_letter_language.strip() or target_position
    subject = (
        f"{role} — отклик — {candidate_name}"
        if russian
        else f"{role} Application — {candidate_name}"
    ).strip(" —")
    return {"subject": subject, "text": text}
