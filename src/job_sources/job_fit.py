import time
from pathlib import Path
from typing import Literal, cast

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from pdfminer.high_level import extract_text
from pydantic import BaseModel, Field

from src.job import Job
from src.job_sources.llm_provider import get_chat_llm
from src.logging import logger

_SCORE_PROMPT = ChatPromptTemplate.from_template(
    """
    Оцени от 1 до 10, насколько кандидат (резюме ниже) подходит для этой
    вакансии. 10 — почти идеальное соответствие опыту и навыкам, 1 — совсем
    не подходит. Если есть конкретные несоответствия (не хватает опыта,
    навыка, языка и т.п.) — перечисли их коротко, 2-4 пункта, не больше.
    Если кандидат полностью подходит — оставь список пустым.

    Отдельно проверь и жёстко занижай балл (до 3 и ниже), если:
    - Грейд вакансии (Junior/Middle/Senior/Lead и т.п., по заголовку и
      требованиям) явно выше реального уровня кандидата, который виден
      по годам опыта и сложности задач в резюме — недостаточный опыт для
      заявленного грейда важнее общего совпадения навыков.
    - В вакансии перечислены обязательные ключевые навыки/технологии,
      которых в резюме нет вообще.
    - Указана зарплата вакансии и зарплатные ожидания кандидата (ниже),
      и вакансия заметно ниже ожиданий.

    Резюме:
    {resume_text}

    Вакансия: {job_title} в {job_company}
    Зарплата вакансии: {job_salary}
    Зарплатные ожидания кандидата: {salary_expectations}
    Описание:
    {job_description}
    """
)

FitTier = Literal["good", "weak", "skip"]

# Метка в gaps: оценку получить не удалось (сбой/лимит ИИ). Вакансия такой
# записью не «закрывается» — журнал считает её готовой к повторной оценке.
SCORING_UNAVAILABLE_GAP = "оценка недоступна (сбой ИИ)"
SCORE_RETRY_PAUSES = (3.0, 10.0)


class FitAssessment(BaseModel):
    """Результат оценки резюме под вакансию — не просто число, а ещё и
    конкретные пробелы, чтобы статистика показывала не только "не
    подошло", но и почему именно."""

    score: int = Field(ge=1, le=10)
    gaps: list[str] = Field(default_factory=list)


def classify_fit(score: int, min_score: float, good_score: float) -> FitTier:
    """Три уровня вместо одного порога: ниже min_score — вообще не
    откликаемся; между min_score и good_score — откликаемся, но это
    помечается как слабый матч в статистике; выше good_score — как
    раньше, без пометок."""
    if score < min_score:
        return "skip"
    if score < good_score:
        return "weak"
    return "good"


def score_job_fit(
    resume_pdf_path: Path,
    job: Job,
    llm_api_key: str,
    salary_expectations: str = "",
) -> FitAssessment:
    """Оценка LLM резюме под вакансию, чтобы прогон не тратил реальный
    отклик на явно неподходящую вакансию и чтобы было видно, чего
    конкретно не хватает. salary_expectations — то же значение, что
    уже вписано в настройках (hh_salary_expectations/
    linkedin_salary_range_usd), просто теперь ещё и участвует в оценке,
    а не только уходит в текст отклика/письма (см. reply_answerer.py).
    При сбое LLM (сеть, лимит, невалидный ответ) — две повторные
    попытки, затем fail closed: оценка 1 с меткой SCORING_UNAVAILABLE_GAP,
    отклик не уходит, а вакансия оценивается заново в следующий раз."""
    resume_text = extract_text(str(resume_pdf_path))
    llm = cast(
        BaseChatModel,
        get_chat_llm(
            llm_api_key,
            temperature=0,
        ),
    )
    chain = _SCORE_PROMPT | llm.with_structured_output(FitAssessment)
    inputs = {
        "resume_text": resume_text,
        "job_title": job.role,
        "job_company": job.company,
        "job_description": job.description,
        "job_salary": job.salary or "не указана",
        "salary_expectations": salary_expectations or "не указаны",
    }
    for pause in (*SCORE_RETRY_PAUSES, None):
        try:
            result = chain.invoke(inputs)
            if result is not None:
                return cast(FitAssessment, result)
        except Exception as e:
            logger.warning(
                f"Оценка вакансии «{job.role}» не получена от ИИ: {e}"
            )
        if pause is not None:
            time.sleep(pause)
    # Fail closed: раньше при сбое возвращалось 10/10 («fail open»), и при
    # лимите ИИ отклики уходили на любые вакансии (живьём 2026-10-08:
    # «Программист 1С» и «Продуктовый аналитик» получили 10/10).
    return FitAssessment(score=1, gaps=[SCORING_UNAVAILABLE_GAP])
