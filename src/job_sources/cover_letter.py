import sys
from pathlib import Path
from typing import Literal

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
    template: Literal[
        "ru_plain", "en_plain", "auto_plain", "html"
    ] = "ru_plain",
) -> str:
    """template="ru_plain" (по умолчанию) — обычный текстовый ответ
    для поля отклика на русскоязычных площадках (HH/GetMatch/
    SuperJob/geekjob/rabota.ru): без HTML/бланка-письма
    (см. plain_cover_letter_prompt/strings.py — почему это отдельный
    от PDF-версии шаблон) и с языком, принудительно закреплённым за
    русским, а не угаданным по тексту вакансии — определяющая ставка
    сделана на площадку, а не на язык конкретного объявления.
    template="en_plain" — тот же обычный текстовый ответ, но на
    английском, для англоязычных площадок с обычным полем/логом
    (wellfound.com, himalayas.app — см. main.
    search_and_apply_wellfound/search_and_apply_himalayas): раньше
    для них тоже брался HTML-шаблон (как у LinkedIn) и HTML-теги
    вручную вырезались после генерации — из-за этого в текст иногда
    просачивались обрывки разметки вроде "><div". Отдельный
    английский plain-текстовый шаблон
    (plain_cover_letter_prompt_en/strings.py) не пишет HTML вообще,
    поэтому вырезать нечего.
    template="auto_plain" — тот же обычный текстовый ответ, но язык
    определяется по тексту вакансии, а не закреплён заранее; для
    LinkedIn (см. main.search_and_apply_linkedin) — там письмо тоже
    только пишется в applied_log/дашборд (см. докстринг той функции:
    отдельного поля под PDF-письмо в форме Easy Apply нет вообще), а
    не прикладывается к отклику как PDF, но вакансии там не всегда на
    одном языке, поэтому в отличие от en_plain язык нельзя закрепить
    жёстко.
    template="html" — HTML-бланк с letterhead
    (cover_letter_prompt/strings.py) для случаев, где письмо реально
    рендерится в PDF-документ (дашборд, resume_facade.py — кнопка
    "Сгенерировать"); ни один из текущих search_and_apply_* его
    больше не использует."""
    template_dir = {
        "ru_plain": "plain_cover_letter_prompt",
        "en_plain": "plain_cover_letter_prompt_en",
        "auto_plain": "plain_cover_letter_prompt_auto",
        "html": "cover_letter_prompt",
    }[template]
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
    # template="ru_plain"/"en_plain" форсируют язык прямо в
    # cover_letter_template — этот сигнал нужен только для
    # template="html"/"auto_plain" (LinkedIn), где язык всё ещё
    # определяется по тексту вакансии:
    # если оно пустое или совсем короткое (у GetMatch search-карточка
    # отдаёт только обрезанный сниппет, иногда пустой — подтверждено
    # на реальном отклике: письмо ушло по-английски на русскую
    # вакансию), угадывать язык не из чего, и LLM по умолчанию пишет
    # на английском. Название и компания почти всегда на языке
    # площадки — добавляем их как минимальный сигнал.
    job_description_text = f"{job.role} — {job.company}\n\n{job.description}"
    answerer.set_job_description_from_text(job_description_text)
    return answerer.generate_cover_letter()
