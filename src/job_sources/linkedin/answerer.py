from typing import Optional

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from src.job import Job
from src.job_sources.llm_provider import get_chat_llm
from src.resume_schemas.job_application_profile import JobApplicationProfile

_ANSWER_PROMPT = ChatPromptTemplate.from_template(
    """
    You are filling out an Easy Apply screening form on behalf of the
    candidate. Answer the question briefly and to the point, using only
    facts from the resume and profile below. Do not invent facts that
    aren't there.

    Always answer in English, regardless of what language the resume,
    profile, or job title/company happen to be in — LinkedIn and this
    form are English-language.

    Candidate's resume:
    {resume_text}

    Candidate's profile:
    {profile_text}

    Job: {job_title} at {job_company}

    Form question: {question}
    {options_hint}

    Reply with only the answer text, no explanations or quotation marks.
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
            f"Pick exactly one option, written exactly as shown: "
            f"{', '.join(options)}"
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
