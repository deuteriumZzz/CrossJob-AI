import sys
from pathlib import Path

from pdfminer.high_level import extract_text

from src.job import Job
from src.libs.resume_and_cover_builder.config import global_config
from src.libs.resume_and_cover_builder.llm import (
    llm_generate_cover_letter_from_job as _llm_clj,
)
from src.libs.resume_and_cover_builder.module_loader import load_module

# В PyInstaller-сборке (desktop_app.spec) __file__ не указывает на
# реальную папку с забандленным cover_letter_prompt/strings.py — он
# распакован в sys._MEIPASS (тот же приём, что main._project_root()/
# StyleManager/ResumeFacade). Без этого фикса сопроводительное письмо
# не сгенерировалось бы вообще ни для одной вакансии ни на одной
# площадке в собранном .exe/.app — это основной, а не только
# дашбордовый путь генерации писем.
_MEIPASS = getattr(sys, "_MEIPASS", None)
_LIB_DIR = (
    Path(_MEIPASS) / "src" / "libs" / "resume_and_cover_builder"
    if _MEIPASS
    else Path(__file__).resolve().parent.parent
    / "libs"
    / "resume_and_cover_builder"
)


def generate_cover_letter_for_job(
    resume_pdf_path: Path, job: Job, llm_api_key: str
) -> str:
    global_config.STRINGS_MODULE_COVER_LETTER_JOB_DESCRIPTION_PATH = (
        _LIB_DIR / "cover_letter_prompt/strings.py"
    )
    global_config.STRINGS_MODULE_NAME = "strings"
    global_config.API_KEY = llm_api_key

    resume_text = extract_text(str(resume_pdf_path))

    strings = load_module(
        str(global_config.STRINGS_MODULE_COVER_LETTER_JOB_DESCRIPTION_PATH),
        global_config.STRINGS_MODULE_NAME,
    )
    answerer = _llm_clj.LLMCoverLetterJobDescription(llm_api_key, strings)
    answerer.set_resume(resume_text)
    answerer.set_job_description_from_text(job.description)
    return answerer.generate_cover_letter()
