from pathlib import Path

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pdfminer.high_level import extract_text

from config import LLM_API_URL, LLM_MODEL, LLM_MODEL_TYPE
from src.job_sources.llm_provider import get_chat_llm

_POSITIONS_PROMPT = ChatPromptTemplate.from_template(
    """
    Ниже — текст резюме. Определи 2-4 наиболее подходящих названия
    должностей (как их обычно ищут на job-сайтах: HeadHunter, SuperJob),
    соответствующих опыту и навыкам этого человека.

    Выведи только сами названия должностей, по одному на строке,
    без нумерации, дефисов и пояснений.

    Резюме:
    {resume_text}
    """
)


def _parse_positions(llm_output: str) -> list[str]:
    return [
        line.strip("-•\t ") for line in llm_output.splitlines() if line.strip()
    ]


def infer_positions_from_resume(
    resume_pdf_path: Path, llm_api_key: str
) -> list[str]:
    """Приблизительно: определяем поисковые должности по тексту резюме,
    когда в work_preferences.yaml поле `positions` оставлено пустым."""
    resume_text = extract_text(str(resume_pdf_path))
    llm = get_chat_llm(
        llm_api_key,
        provider=LLM_MODEL_TYPE,
        model=LLM_MODEL,
        temperature=0.3,
        base_url=LLM_API_URL or None,
    )
    chain = _POSITIONS_PROMPT | llm | StrOutputParser()
    output = chain.invoke({"resume_text": resume_text})
    return _parse_positions(output)


_PLAIN_TEXT_RESUME_PROMPT = ChatPromptTemplate.from_template(
    """
    Ниже — текст резюме. Разложи его в YAML со СТРОГО такими корневыми
    ключами (пропускай ключ целиком, если в резюме для него нет
    данных): personal_information (name, surname, country, city,
    address, zip_code, phone_prefix, phone, email, github, linkedin),
    education_details (список: education_level, institution,
    field_of_study, final_evaluation_grade, start_date,
    year_of_completion), experience_details (список: position,
    company, employment_period, location, industry,
    key_responsibilities как список строк, skills_acquired как список
    строк), projects (список: name, description, link), achievements
    (список: name, description), certifications (список: name,
    description), languages (список: language, proficiency),
    interests (список строк).

    Выведи ТОЛЬКО валидный YAML, без markdown-обрамления ```, без
    пояснений до или после.

    Резюме:
    {resume_text}
    """
)


def extract_plain_text_resume(resume_pdf_path: Path, llm_api_key: str) -> str:
    """Разово превращает resume.pdf в YAML под структуру Resume
    (см. src/resume_schemas/resume.py) — нужен только трём старым
    пунктам меню (Generate Resume*), которые всё ещё читают
    plain_text_resume.yaml, а не resume.pdf напрямую."""
    resume_text = extract_text(str(resume_pdf_path))
    llm = get_chat_llm(
        llm_api_key,
        provider=LLM_MODEL_TYPE,
        model=LLM_MODEL,
        temperature=0,
        base_url=LLM_API_URL or None,
    )
    chain = _PLAIN_TEXT_RESUME_PROMPT | llm | StrOutputParser()
    output = chain.invoke({"resume_text": resume_text})
    return output.strip().removeprefix("```yaml").removesuffix("```").strip()
