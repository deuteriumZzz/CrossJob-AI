"""Справка к интервью: вероятные вопросы по вакансии с тезисами ответа
из резюме, как говорить о слабых местах (gaps из оценки вакансии) и что
спросить у работодателя. Генерируется, когда отклик доходит до этапа
"интервью" (или по кнопке в дашборде)."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pdfminer.high_level import extract_text
from pydantic import BaseModel, Field

from src.job_sources.llm_provider import get_chat_llm

_PREP_PROMPT = ChatPromptTemplate.from_template(
    """
    Подготовь кандидата к интервью. Пиши по-русски, коротко, списками.
    Используй только факты из резюме — не придумывай опыт, цифры и факты
    о компании (о компании ты знаешь только название; если без фактов о
    ней не обойтись — так и напиши "проверьте на сайте компании").

    Вакансия: {job_title} в {job_company}
    Ссылка: {job_link}
    Чего не хватает кандидату по оценке вакансии: {gaps}

    Резюме:
    {resume_text}

    Структура ответа:
    1. Вероятные вопросы (8 штук: технические по этой роли и
       поведенческие) — к каждому 1–2 тезиса ответа из резюме.
    2. Слабые места — по каждому пункту "чего не хватает": как честно
       ответить и чем компенсировать.
    3. Три вопроса, которые стоит задать работодателю.
    """
)


def generate_interview_prep(
    resume_pdf_path: Path,
    job_title: str,
    job_company: str,
    job_link: str,
    gaps: list[str],
    llm_api_key: str,
) -> str:
    chain = _PREP_PROMPT | get_chat_llm(llm_api_key, temperature=0.3) | StrOutputParser()
    return chain.invoke(
        {
            "resume_text": extract_text(str(resume_pdf_path)),
            "job_title": job_title,
            "job_company": job_company,
            "job_link": job_link,
            "gaps": "; ".join(gaps) or "не указано",
        }
    ).strip()


# --- Тренажёр интервью (дашборд: вопрос → ваш ответ → разбор) ----------

_QUESTIONS_PROMPT = ChatPromptTemplate.from_template(
    """
    Составь 8 вопросов, которые реально зададут на интервью на позицию
    {job_title} в {job_company}: 5 технических по этой роли и 3
    поведенческих. Отдельно затронь слабые места кандидата: {gaps}.
    Вопросы по-русски, каждый — одно предложение.
    """
)

_FEEDBACK_PROMPT = ChatPromptTemplate.from_template(
    """
    Ты интервьюер на позицию {job_title}. Оцени ответ кандидата по-русски,
    коротко: что хорошо, чего не хватает, и как ответить сильнее (2–4
    предложения примерного ответа, только на фактах из резюме — не
    придумывай опыт). В конце оценка от 1 до 10.

    Резюме:
    {resume_text}

    Вопрос: {question}
    Ответ кандидата: {answer}
    """
)


class _Questions(BaseModel):
    questions: list[str] = Field(description="8 вопросов интервью")


def generate_questions(
    job_title: str, job_company: str, gaps: list[str], llm_api_key: str
) -> list[str]:
    llm = cast(BaseChatModel, get_chat_llm(llm_api_key, temperature=0.4))
    result = cast(
        _Questions,
        llm.with_structured_output(_Questions).invoke(
            _QUESTIONS_PROMPT.format(
                job_title=job_title,
                job_company=job_company,
                gaps="; ".join(gaps) or "не указаны",
            )
        ),
    )
    return [q.strip() for q in result.questions if q.strip()][:8]


def evaluate_answer(
    resume_pdf_path: Path,
    job_title: str,
    question: str,
    answer: str,
    llm_api_key: str,
) -> str:
    chain = _FEEDBACK_PROMPT | get_chat_llm(llm_api_key, temperature=0.2) | StrOutputParser()
    return chain.invoke(
        {
            "resume_text": extract_text(str(resume_pdf_path)),
            "job_title": job_title,
            "question": question,
            "answer": answer,
        }
    ).strip()
