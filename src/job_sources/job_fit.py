from pathlib import Path
from typing import Literal, cast

from langchain_core.prompts import ChatPromptTemplate
from pdfminer.high_level import extract_text
from pydantic import BaseModel, Field

from src.job import Job
from src.job_sources.llm_provider import get_chat_llm

_SCORE_PROMPT = ChatPromptTemplate.from_template(
    """
    Оцени от 1 до 10, насколько кандидат (резюме ниже) подходит для этой
    вакансии. 10 — почти идеальное соответствие опыту и навыкам, 1 — совсем
    не подходит. Если есть конкретные несоответствия (не хватает опыта,
    навыка, языка и т.п.) — перечисли их коротко, 2-4 пункта, не больше.
    Если кандидат полностью подходит — оставь список пустым.

    Резюме:
    {resume_text}

    Вакансия: {job_title} в {job_company}
    Описание:
    {job_description}
    """
)

FitTier = Literal["good", "weak", "skip"]


class FitAssessment(BaseModel):
    """Результат оценки резюме под вакансию — не просто число, а ещё и
    конкретные пробелы, чтобы статистика показывала не только "не
    подошло", но и почему именно."""

    score: int = Field(ge=1, le=10)
    gaps: list[str] = Field(default_factory=list)


def classify_fit(score: int, min_score: int, good_score: int) -> FitTier:
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
    resume_pdf_path: Path, job: Job, llm_api_key: str
) -> FitAssessment:
    """Оценка LLM резюме под вакансию, чтобы прогон не тратил реальный
    отклик на явно неподходящую вакансию и чтобы было видно, чего
    конкретно не хватает. При сбое LLM (сеть, невалидный ответ) —
    fail open: считаем матч хорошим и без пробелов, чтобы кривой ответ
    модели не заблокировал молча все отклики."""
    resume_text = extract_text(str(resume_pdf_path))
    llm = get_chat_llm(
        llm_api_key,
        temperature=0,
    )
    chain = _SCORE_PROMPT | llm.with_structured_output(FitAssessment)
    try:
        result = chain.invoke(
            {
                "resume_text": resume_text,
                "job_title": job.role,
                "job_company": job.company,
                "job_description": job.description,
            }
        )
        return cast(FitAssessment, result)
    except Exception:
        return FitAssessment(score=10, gaps=[])
