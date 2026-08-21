"""
Генерирует HTML сопроводительного письма под конкретную вакансию
и резюме — в PDF его конвертирует HTML_to_PDF из utils, этот
класс отвечает только за текст.
"""

# app/libs/resume_and_cover_builder/llm_generate_cover_letter_from_job.py
import os
import textwrap
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import OpenAIEmbeddings
from loguru import logger

from src.job_sources.llm_provider import get_chat_llm

from ..utils import LoggerChatModel

# Загружаем переменные окружения из .env
load_dotenv()

# Настраиваем файл логов
log_folder = "log/cover_letter/gpt_cover_letter_job_descr"
if not os.path.exists(log_folder):
    os.makedirs(log_folder)
log_path = Path(log_folder).resolve()
logger.add(
    log_path / "gpt_cover_letter_job_descr.log",
    rotation="1 day",
    compression="zip",
    retention="7 days",
    level="DEBUG",
)


class LLMCoverLetterJobDescription:
    def __init__(self, openai_api_key, strings):
        self.llm_cheap = LoggerChatModel(
            get_chat_llm(
                openai_api_key,
                temperature=0.4,
            )
        )
        self.llm_embeddings = OpenAIEmbeddings(openai_api_key=openai_api_key)
        self.strings = strings

    @staticmethod
    def _preprocess_template_string(template: str) -> str:
        """
        Шаблоны в strings-модулях объявлены с отступом кода Python
        — dedent убирает его, иначе LLM получит промпт с лишними
        пробелами в каждой строке.
        """
        return textwrap.dedent(template)

    def set_resume(self, resume) -> None:
        """Сохраняет текст резюме для подстановки в промпт."""
        self.resume = resume

    def set_job_description_from_text(self, job_description_text) -> None:
        """
        Описание вакансии сначала сжимается отдельным
        summarization-промптом — итоговый промпт письма не
        раздувается полным текстом вакансии.
        """
        logger.debug("Starting job description summarization...")
        prompt = ChatPromptTemplate.from_template(
            self.strings.summarize_prompt_template
        )
        chain = prompt | self.llm_cheap | StrOutputParser()
        output = chain.invoke({"text": job_description_text})
        self.job_description = output
        logger.debug(
            f"Job description summarization complete: {self.job_description}"
        )

    def generate_cover_letter(self) -> str:
        """Генерирует текст письма по резюме и (уже сжатому)
        описанию вакансии."""
        logger.debug("Starting cover letter generation...")
        prompt_template = self._preprocess_template_string(
            self.strings.cover_letter_template
        )
        logger.debug(
            f"Cover letter template after preprocessing: {prompt_template}"
        )

        prompt = ChatPromptTemplate.from_template(prompt_template)
        logger.debug(f"Prompt created: {prompt}")

        chain = prompt | self.llm_cheap | StrOutputParser()
        logger.debug(f"Chain created: {chain}")

        input_data = {
            "job_description": self.job_description,
            "resume": self.resume,
        }
        logger.debug(f"Input data: {input_data}")

        output = chain.invoke(input_data)
        logger.debug(f"Cover letter generation result: {output}")

        logger.debug("Cover letter generation completed")
        return output
