from __future__ import annotations

from pathlib import Path

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pdfminer.high_level import extract_text

from config import LLM_API_URL, LLM_MODEL, LLM_MODEL_TYPE
from src.job_sources.llm_provider import get_chat_llm

_REPLY_PROMPT = ChatPromptTemplate.from_template(
    """
    Ты отвечаешь от лица кандидата на сообщение работодателя в
    переписке по вакансии на HeadHunter. Используй только факты из
    резюме и данных ниже. Если ответа на конкретный вопрос там нет —
    ответь честно и обобщённо, не выдумывай цифры и факты (особенно
    зарплату и опыт).

    Резюме (PDF):
    {resume_text}

    Резюме на HH:
    {hh_resume_summary}

    Пожелания кандидата:
    {preferences_summary}

    {github_summary}

    Вакансия: {job_title} в {job_company}

    Сообщение работодателя:
    {message_text}

    Ответь одним связным сообщением, как в чате — коротко, по делу,
    без приветствия и подписи (диалог уже открыт).
    """
)


def build_preferences_summary(parameters: dict) -> str:
    """Собирает то, что реально пригодится в ответе HR (зарплата,
    формат работы, локации) из уже существующих полей
    work_preferences.yaml — новых полей не требует, кроме
    необязательного salary_expectations."""
    parts = []
    salary = parameters.get("salary_expectations")
    if salary:
        parts.append(f"Ожидаемая зарплата: {salary}")
    work_format = [
        name
        for name, key in (
            ("удалённо", "remote"),
            ("гибрид", "hybrid"),
            ("в офисе", "onsite"),
        )
        if parameters.get(key)
    ]
    if work_format:
        parts.append(f"Формат работы: {', '.join(work_format)}")
    locations = parameters.get("locations")
    if locations:
        parts.append(f"Локации: {', '.join(locations)}")
    return "\n".join(parts) if parts else "Не указаны."


def build_hh_resume_summary(hh_resume: dict) -> str:
    """hh_resume — сырой JSON из HeadHunterClient.get_resume(); поля
    не проверены на живом аккаунте, читаем защитно через .get()."""
    if not hh_resume:
        return "Недоступно."
    parts = []
    salary = hh_resume.get("salary") or {}
    if salary.get("amount"):
        parts.append(
            f"Зарплата в резюме: {salary['amount']} "
            f"{salary.get('currency', '')}".strip()
        )
    skills = hh_resume.get("skill_set") or []
    if skills:
        parts.append(f"Навыки: {', '.join(skills)}")
    return "\n".join(parts) if parts else "Не указано."


def generate_reply(
    resume_pdf_path: Path,
    message_text: str,
    job_title: str,
    job_company: str,
    preferences_summary: str,
    llm_api_key: str,
    hh_resume_summary: str = "Недоступно.",
    github_summary: str = "",
) -> str:
    resume_text = extract_text(str(resume_pdf_path))
    llm = get_chat_llm(
        llm_api_key,
        provider=LLM_MODEL_TYPE,
        model=LLM_MODEL,
        temperature=0.3,
        base_url=LLM_API_URL or None,
    )
    chain = _REPLY_PROMPT | llm | StrOutputParser()
    output = chain.invoke(
        {
            "resume_text": resume_text,
            "hh_resume_summary": hh_resume_summary,
            "preferences_summary": preferences_summary,
            "github_summary": github_summary,
            "job_title": job_title,
            "job_company": job_company,
            "message_text": message_text,
        }
    )
    return output.strip()
