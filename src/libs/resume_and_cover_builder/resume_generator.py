"""
Выбирает нужный LLM-класс (обычное резюме, резюме или письмо под
конкретную вакансию) и общий HTML-шаблон — единая точка сборки,
чтобы facade не знал про конкретные LLM-классы.
"""

# app/libs/resume_and_cover_builder/resume_generator.py
from string import Template
from typing import Any

from src.libs.resume_and_cover_builder.llm import (
    llm_generate_cover_letter_from_job as _llm_clj,
)
from src.libs.resume_and_cover_builder.llm import (
    llm_generate_resume_from_job as _llm_rj,
)
from src.libs.resume_and_cover_builder.llm.llm_generate_resume import (
    LLMResumer,
)

from .config import global_config
from .module_loader import load_module


class ResumeGenerator:
    def __init__(self):
        pass

    def set_resume_object(self, resume_object):
        self.resume_object = resume_object

    def _create_resume(self, gpt_answerer: Any, style_path):
        # Устанавливаем резюме в объект gpt_answerer
        gpt_answerer.set_resume(self.resume_object)

        # Читаем HTML-шаблон
        template = Template(global_config.html_template)

        try:
            with open(style_path, "r") as f:
                style_css = f.read()
        except FileNotFoundError:
            raise ValueError(
                f"Il file di stile non è stato trovato nel percorso: "
                f"{style_path}"
            )
        except Exception as e:
            raise RuntimeError(f"Errore durante la lettura del file CSS: {e}")

        # Генерируем HTML резюме
        body_html = gpt_answerer.generate_html_resume()

        # Подставляем содержимое в шаблон
        return template.substitute(body=body_html, style_css=style_css)

    def create_resume(self, style_path):
        strings = load_module(
            global_config.STRINGS_MODULE_RESUME_PATH,
            global_config.STRINGS_MODULE_NAME,
        )
        gpt_answerer = LLMResumer(global_config.API_KEY, strings)
        return self._create_resume(gpt_answerer, style_path)

    def create_resume_job_description_text(
        self, style_path: str, job_description_text: str
    ):
        strings = load_module(
            str(global_config.STRINGS_MODULE_RESUME_JOB_DESCRIPTION_PATH),
            global_config.STRINGS_MODULE_NAME,
        )
        gpt_answerer = _llm_rj.LLMResumeJobDescription(
            global_config.API_KEY, strings
        )
        gpt_answerer.set_job_description_from_text(job_description_text)
        return self._create_resume(gpt_answerer, style_path)

    def create_cover_letter_job_description(
        self, style_path: str, job_description_text: str
    ):
        strings = load_module(
            str(
                global_config.STRINGS_MODULE_COVER_LETTER_JOB_DESCRIPTION_PATH
            ),
            global_config.STRINGS_MODULE_NAME,
        )
        gpt_answerer = _llm_clj.LLMCoverLetterJobDescription(
            global_config.API_KEY, strings
        )
        gpt_answerer.set_resume(self.resume_object)
        gpt_answerer.set_job_description_from_text(job_description_text)
        cover_letter_html = gpt_answerer.generate_cover_letter()
        template = Template(global_config.html_template)
        with open(style_path, "r") as f:
            style_css = f.read()
        return template.substitute(body=cover_letter_html, style_css=style_css)
