"""
LLMResumeJobDescription переопределяет каждый generate_* из
LLMResumer, добавляя job_description к данным резюме — так LLM
подгоняет содержимое каждой секции под конкретную вакансию.
"""

# app/libs/resume_and_cover_builder/llm_generate_resume_from_job.py
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from loguru import logger

from src.libs.resume_and_cover_builder.llm.llm_generate_resume import (
    LLMResumer,
)

# Загружаем переменные окружения из .env
load_dotenv()

log_folder = "log/resume/gpt_resum_job_descr"
if not os.path.exists(log_folder):
    os.makedirs(log_folder)
log_path = Path(log_folder).resolve()
logger.add(
    log_path / "gpt_resum_job_descr.log",
    rotation="1 day",
    compression="zip",
    retention="7 days",
    level="DEBUG",
)


class LLMResumeJobDescription(LLMResumer):
    def __init__(self, openai_api_key, strings):
        super().__init__(openai_api_key, strings)

    def set_job_description_from_text(self, job_description_text) -> None:
        """
        Описание вакансии сначала сжимается отдельным
        summarization-промптом — итоговые промпты секций резюме не
        раздуваются полным текстом вакансии.
        """
        prompt = ChatPromptTemplate.from_template(
            self.strings.summarize_prompt_template
        )
        chain = prompt | self.llm_cheap | StrOutputParser()
        output = chain.invoke({"text": job_description_text})
        self.job_description = output

    def generate_header(self, data: Any = None) -> str:
        """Как у родителя, но с job_description в data — под неё
        LLM подстраивает формулировки секции."""
        return super().generate_header(
            data={
                "personal_information": self.resume.personal_information,
                "job_description": self.job_description,
            }
        )

    def generate_education_section(self, data: Any = None) -> str:
        """Как у родителя, но с job_description в data — под неё
        LLM подстраивает формулировки секции."""
        return super().generate_education_section(
            data={
                "education_details": self.resume.education_details,
                "job_description": self.job_description,
            }
        )

    def generate_work_experience_section(self, data: Any = None) -> str:
        """Как у родителя, но с job_description в data — под неё
        LLM подстраивает формулировки секции."""
        return super().generate_work_experience_section(
            data={
                "experience_details": self.resume.experience_details,
                "job_description": self.job_description,
            }
        )

    def generate_projects_section(self, data: Any = None) -> str:
        """Как у родителя, но с job_description в data — под неё
        LLM подстраивает формулировки секции."""
        return super().generate_projects_section(
            data={
                "projects": self.resume.projects,
                "job_description": self.job_description,
            }
        )

    def generate_achievements_section(self, data: Any = None) -> str:
        """Как у родителя, но с job_description в data — под неё
        LLM подстраивает формулировки секции."""
        return super().generate_achievements_section(
            data={
                "achievements": self.resume.achievements,
                "job_description": self.job_description,
            }
        )

    def generate_certifications_section(self, data: Any = None) -> str:
        """Как у родителя, но с job_description в data — под неё
        LLM подстраивает формулировки секции."""
        return super().generate_certifications_section(
            data={
                "certifications": self.resume.certifications,
                "job_description": self.job_description,
            }
        )

    def generate_additional_skills_section(self, data: Any = None) -> str:
        """
        В отличие от остальных секций не делегирует в super(),
        потому что родительская реализация не принимает
        job_description через data — здесь та же логика повторена
        с добавлением job_description в вызов LLM.
        """
        additional_skills_prompt_template = self._preprocess_template_string(
            self.strings.prompt_additional_skills
        )
        skills = set()
        if self.resume.experience_details:
            for exp in self.resume.experience_details:
                if exp.skills_acquired:
                    skills.update(exp.skills_acquired)

        if self.resume.education_details:
            for edu in self.resume.education_details:
                if edu.exam:
                    for exam in edu.exam:
                        skills.update(exam.keys())
        prompt = ChatPromptTemplate.from_template(
            additional_skills_prompt_template
        )
        chain = prompt | self.llm_cheap | StrOutputParser()
        output = chain.invoke(
            {
                "languages": self.resume.languages,
                "interests": self.resume.interests,
                "skills": skills,
                "job_description": self.job_description,
            }
        )
        return output
