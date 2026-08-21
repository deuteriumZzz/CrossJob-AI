from typing import Optional

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from src.job import Job
from src.job_sources.llm_provider import get_chat_llm
from src.resume_schemas.job_application_profile import JobApplicationProfile

_ANSWER_PROMPT = ChatPromptTemplate.from_template(
    """
    Ты заполняешь анкету Easy Apply от имени кандидата. Ответь на вопрос
    коротко и по делу, используя только факты из резюме и профиля ниже.
    Не выдумывай факты, которых там нет.

    Резюме кандидата:
    {resume_text}

    Профиль кандидата:
    {profile_text}

    Вакансия: {job_title} в {job_company}

    Вопрос анкеты: {question}
    {options_hint}

    Ответь только текстом ответа, без пояснений и кавычек.
    """
)


class EasyApplyAnswerer:
    def __init__(
        self,
        resume_text: str,
        profile: JobApplicationProfile,
        job: Job,
        llm_api_key: str,
    ):
        self.resume_text = resume_text
        self.profile_text = str(profile)
        self.job = job
        llm = get_chat_llm(
            llm_api_key,
            temperature=0.2,
        )
        self.chain = _ANSWER_PROMPT | llm | StrOutputParser()

    def answer(self, question: str, options: Optional[list] = None) -> str:
        options_hint = (
            f"Выбери один вариант ровно как он написан: {', '.join(options)}"
            if options
            else ""
        )
        result = self.chain.invoke(
            {
                "resume_text": self.resume_text,
                "profile_text": self.profile_text,
                "job_title": self.job.role,
                "job_company": self.job.company,
                "question": question,
                "options_hint": options_hint,
            }
        )
        return result.strip()
