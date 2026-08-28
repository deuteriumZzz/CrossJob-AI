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
    resume_pdf_path: Path,
    job: Job,
    llm_api_key: str,
    force_russian: bool = True,
) -> str:
    """force_russian=True (по умолчанию) — обычный текстовый ответ
    для поля отклика на русскоязычных площадках (HH/GetMatch/
    SuperJob/geekjob/rabota.ru): без HTML/бланка-письма
    (см. plain_cover_letter_prompt/strings.py — почему это отдельный
    от PDF-версии шаблон) и с языком, принудительно закреплённым за
    русским, а не угаданным по тексту вакансии — определяющая ставка
    сделана на площадку, а не на язык конкретного объявления.
    force_russian=False — для LinkedIn (см. main.
    search_and_apply_linkedin): там нужен оформленный PDF-документ
    (площадка ожидает приложение), поэтому используется прежний
    HTML-шаблон с определением языка по тексту вакансии."""
    template_dir = (
        "plain_cover_letter_prompt" if force_russian else "cover_letter_prompt"
    )
    global_config.STRINGS_MODULE_COVER_LETTER_JOB_DESCRIPTION_PATH = (
        _LIB_DIR / template_dir / "strings.py"
    )
    global_config.STRINGS_MODULE_NAME = "strings"
    global_config.API_KEY = llm_api_key
    # LOG_OUTPUT_FILE_PATH раньше выставлял только дашбордовый
    # ResumeFacade (кнопка "Сгенерировать") — обычный автооткликер
    # (main.py --auto ...) никогда через него не проходит, так что
    # LLMLogger.log_request падал на None/"open_ai_calls.json" при
    # КАЖДОМ письме. Раньше это тихо прятал старый 15-попыточный
    # ретрай-цикл в LoggerChatModel (см. utils.py) — он слепо повторял
    # эту детерминированную ошибку как будто это рейт-лимит, отсюда и
    # были прогоны по 20+ минут на одно письмо. Выставляем сами, а не
    # полагаемся на то, что кто-то сделал это раньше нас.
    if global_config.LOG_OUTPUT_FILE_PATH is None:
        global_config.LOG_OUTPUT_FILE_PATH = resume_pdf_path.parent

    resume_text = extract_text(str(resume_pdf_path))

    strings = load_module(
        str(global_config.STRINGS_MODULE_COVER_LETTER_JOB_DESCRIPTION_PATH),
        global_config.STRINGS_MODULE_NAME,
    )
    answerer = _llm_clj.LLMCoverLetterJobDescription(llm_api_key, strings)
    answerer.set_resume(resume_text)
    # force_russian=True форсирует русский прямо в cover_letter_
    # template — этот сигнал нужен только для force_russian=False
    # (LinkedIn), где язык всё ещё определяется по тексту вакансии:
    # если оно пустое или совсем короткое (у GetMatch search-карточка
    # отдаёт только обрезанный сниппет, иногда пустой — подтверждено
    # на реальном отклике: письмо ушло по-английски на русскую
    # вакансию), угадывать язык не из чего, и LLM по умолчанию пишет
    # на английском. Название и компания почти всегда на языке
    # площадки — добавляем их как минимальный сигнал.
    job_description_text = f"{job.role} — {job.company}\n\n{job.description}"
    answerer.set_job_description_from_text(job_description_text)
    return answerer.generate_cover_letter()
