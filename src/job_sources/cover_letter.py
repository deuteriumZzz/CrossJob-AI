from pathlib import Path

from pdfminer.high_level import extract_text

from src.job import Job
from src.libs.resume_and_cover_builder.config import global_config
from src.libs.resume_and_cover_builder.llm import (
    llm_generate_cover_letter_from_job as _llm_clj,
)
from src.libs.resume_and_cover_builder.module_loader import load_module

_LIB_DIR = (
    Path(__file__).resolve().parent.parent
    / "libs"
    / "resume_and_cover_builder"
)


def generate_cover_letter_for_job(
    resume_pdf_path: Path, job: Job, llm_api_key: str
) -> str:
    global_config.STRINGS_MODULE_COVER_LETTER_JOB_DESCRIPTION_PATH = (
        _LIB_DIR / "cover_letter_prompt/strings_feder-cr.py"
    )
    global_config.STRINGS_MODULE_NAME = "strings_feder_cr"
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
