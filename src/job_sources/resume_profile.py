from pathlib import Path

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pdfminer.high_level import extract_text
from pydantic import SecretStr

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
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        api_key=SecretStr(llm_api_key),
        temperature=0.3,
    )
    chain = _POSITIONS_PROMPT | llm | StrOutputParser()
    output = chain.invoke({"resume_text": resume_text})
    return _parse_positions(output)
