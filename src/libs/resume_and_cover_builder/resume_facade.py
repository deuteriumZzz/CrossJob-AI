"""
Фасад над ResumeGenerator/StyleManager/LLMParser: main.py вызывает
только методы create_*, не зная, что за ними сначала настраивается
общий global_config, а затем идёт LLM-конвейер генерации.
"""

# app/libs/resume_and_cover_builder/manager_facade.py
import hashlib
from pathlib import Path

import inquirer
from loguru import logger

from src.job import Job
from src.libs.resume_and_cover_builder.llm.llm_job_parser import LLMParser
from src.utils.chrome_utils import HTML_to_PDF

from .config import global_config


class ResumeFacade:
    def __init__(
        self,
        api_key,
        style_manager,
        resume_generator,
        resume_object,
        output_path,
    ):
        """
        Пути к prompt-модулям и стилям вычисляются здесь один раз
        и кладутся в общий global_config, чтобы ResumeGenerator и
        LLM-классы ниже по стеку не принимали их отдельно в каждом
        вызове.
        """
        lib_directory = Path(__file__).resolve().parent
        global_config.STRINGS_MODULE_RESUME_PATH = (
            lib_directory / "resume_prompt/strings.py"
        )
        global_config.STRINGS_MODULE_RESUME_JOB_DESCRIPTION_PATH = (
            lib_directory / "resume_job_description_prompt/strings.py"
        )
        global_config.STRINGS_MODULE_COVER_LETTER_JOB_DESCRIPTION_PATH = (
            lib_directory / "cover_letter_prompt/strings.py"
        )
        global_config.STRINGS_MODULE_NAME = "strings"
        global_config.STYLES_DIRECTORY = lib_directory / "resume_style"
        global_config.LOG_OUTPUT_FILE_PATH = output_path
        global_config.API_KEY = api_key
        self.style_manager = style_manager
        self.resume_generator = resume_generator
        self.resume_generator.set_resume_object(resume_object)
        self.selected_style = None  # хранит выбранный стиль

    def set_driver(self, driver):
        self.driver = driver

    def prompt_user(self, choices: list[str], message: str) -> str:
        """Задаёт пользователю вопрос со списком вариантов через
        inquirer и возвращает выбранный."""
        questions = [
            inquirer.List("selection", message=message, choices=choices),
        ]
        return inquirer.prompt(questions)["selection"]

    def prompt_for_text(self, message: str) -> str:
        """Запрашивает у пользователя свободный текстовый ввод
        через inquirer."""
        questions = [
            inquirer.Text("text", message=message),
        ]
        return inquirer.prompt(questions)["text"]

    def link_to_job(self, job_url):
        self.driver.get(job_url)
        self.driver.implicitly_wait(10)
        body_element = self.driver.find_element("tag name", "body")
        body_element = body_element.get_attribute("outerHTML")
        self.llm_job_parser = LLMParser(openai_api_key=global_config.API_KEY)
        self.llm_job_parser.set_body_html(body_element)

        self.job = Job()
        self.job.role = self.llm_job_parser.extract_role()
        self.job.company = self.llm_job_parser.extract_company_name()
        self.job.description = self.llm_job_parser.extract_job_description()
        self.job.location = self.llm_job_parser.extract_location()
        self.job.link = job_url
        logger.info(f"Extracting job details from URL: {job_url}")

    def create_resume_pdf_job_tailored(self) -> tuple[bytes, str]:
        """
        Резюме подгоняется под конкретную вакансию (self.job),
        поэтому имя файла выводится из хэша ссылки на вакансию —
        один и тот же job_url всегда даёт одно и то же имя файла.
        """
        style_path = self.style_manager.get_style_path()
        if style_path is None:
            raise ValueError(
                "You must choose a style before generating the PDF."
            )

        html_resume = self.resume_generator.create_resume_job_description_text(
            style_path, self.job.description
        )

        # Уникальное имя файла — хэш от ссылки на вакансию
        suggested_name = hashlib.md5(self.job.link.encode()).hexdigest()[:10]

        result = HTML_to_PDF(html_resume, self.driver)
        self.driver.quit()
        return result, suggested_name

    def create_resume_pdf(self) -> str:
        """Генерирует PDF резюме по выбранному стилю без привязки
        к конкретной вакансии."""
        style_path = self.style_manager.get_style_path()
        if style_path is None:
            raise ValueError(
                "You must choose a style before generating the PDF."
            )

        html_resume = self.resume_generator.create_resume(style_path)
        result = HTML_to_PDF(html_resume, self.driver)
        self.driver.quit()
        return result

    def create_cover_letter(self) -> tuple[bytes, str]:
        """
        Как и в резюме под вакансию: имя файла — хэш ссылки на
        вакансию, чтобы повторная генерация для того же job_url не
        плодила разные имена.
        """
        style_path = self.style_manager.get_style_path()
        if style_path is None:
            raise ValueError(
                "You must choose a style before generating the PDF."
            )

        cover_letter_html = (
            self.resume_generator.create_cover_letter_job_description(
                style_path, self.job.description
            )
        )

        # Уникальное имя файла — хэш от ссылки на вакансию
        suggested_name = hashlib.md5(self.job.link.encode()).hexdigest()[:10]

        result = HTML_to_PDF(cover_letter_html, self.driver)
        self.driver.quit()
        return result, suggested_name
