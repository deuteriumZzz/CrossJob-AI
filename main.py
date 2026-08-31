import base64
import binascii
import re
import shutil
import sys
import time
import traceback
from contextlib import nullcontext
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal, Optional, Tuple

import click
import inquirer
import yaml
from pdfminer.high_level import extract_text as extract_pdf_text
from selenium.webdriver.common.by import By

from config import (
    DAILY_APPLICATION_LIMIT,
    JOB_MAX_APPLICATIONS,
    JOB_MIN_SCORE,
    JOB_SUITABILITY_SCORE,
    LINKEDIN_DAILY_APPLICATION_LIMIT,
    LLM_MODEL_TYPE,
)
from src.config_patch import set_source_field, set_top_level_field
from src.job import Job
from src.job_sources.applied_log import AppliedLog
from src.job_sources.apply_pacing import (
    randomized_daily_limit,
    wait_before_apply,
    wait_before_telegram_message,
    wait_between_sources,
    within_active_hours,
)
from src.job_sources.base import JobSource
from src.job_sources.block_detection import (
    PlatformBlockedError,
    is_still_blocked,
    mark_blocked,
)
from src.job_sources.cover_letter import generate_cover_letter_for_job
from src.job_sources.geekjob.auth import GeekjobSession
from src.job_sources.geekjob.client import GeekjobClient
from src.job_sources.geekjob.source import GeekjobSource
from src.job_sources.getmatch.auth import GetMatchSession
from src.job_sources.getmatch.client import GetMatchClient
from src.job_sources.getmatch.source import GetMatchSource
from src.job_sources.github_context import fetch_github_summary
from src.job_sources.habr_career.auth import HabrCareerSession
from src.job_sources.habr_career.client import HabrCareerClient
from src.job_sources.habr_career.source import HabrCareerSource
from src.job_sources.headhunter.browser_client import HeadHunterBrowserClient
from src.job_sources.headhunter.browser_negotiations import (
    list_withdrawable_negotiations,
    withdraw_negotiation,
)
from src.job_sources.headhunter.browser_replies import (
    block_employer,
    fetch_new_employer_messages,
    find_external_link,
    send_reply,
)
from src.job_sources.headhunter.browser_resume import (
    clone_resume,
    start_resume_draft,
)
from src.job_sources.headhunter.browser_session import HeadHunterSession
from src.job_sources.headhunter.browser_source import HeadHunterBrowserSource
from src.job_sources.headhunter.form_fill import (
    answers_to_dicts,
    dicts_to_answers,
    dicts_to_questions,
    draft_form_answers,
    fill_form,
    format_questions_and_answers,
    questions_to_dicts,
    scrape_form_questions,
)
from src.job_sources.headhunter.telegram_approval import (
    get_pending_form,
    notify_pending_form,
    poll_form_commands,
    remove_pending_form,
    save_pending_form,
    update_pending_form_answers,
)
from src.job_sources.job_fit import classify_fit, score_job_fit
from src.job_sources.linkedin.answerer import EasyApplyAnswerer
from src.job_sources.linkedin.auth import LinkedInSession
from src.job_sources.linkedin.easy_apply import run_easy_apply
from src.job_sources.linkedin.source import LinkedInSource
from src.job_sources.llm_provider import (
    get_active_provider as get_active_llm_provider,
)
from src.job_sources.llm_provider import (
    set_fallback_base_urls as set_llm_fallback_base_urls,
)
from src.job_sources.llm_provider import (
    set_fallback_enabled as set_llm_fallback_enabled,
)
from src.job_sources.llm_provider import (
    set_fallback_keys as set_llm_fallback_keys,
)
from src.job_sources.llm_provider import (
    set_fallback_mode as set_llm_fallback_mode,
)
from src.job_sources.llm_provider import (
    set_provider_override as set_llm_provider_override,
)
from src.job_sources.llm_usage import (
    check_and_mark_alert,
    check_and_mark_llm_exhausted_alert,
)
from src.job_sources.llm_usage import (
    set_output_folder as set_llm_usage_output_folder,
)
from src.job_sources.rabota_ru.auth import RabotaRuSession
from src.job_sources.rabota_ru.client import RabotaRuClient
from src.job_sources.rabota_ru.source import RabotaRuSource
from src.job_sources.reply_answerer import (
    build_preferences_summary,
    generate_reply,
    message_needs_reply,
)
from src.job_sources.reply_check import print_superjob_replies
from src.job_sources.resume_profile import (
    extract_plain_text_resume,
    infer_positions_from_resume,
)
from src.job_sources.superjob.auth import SuperJobAuth
from src.job_sources.superjob.client import SuperJobClient
from src.job_sources.superjob.source import SuperJobSource
from src.job_sources.telegram.client import TelegramSourceClient
from src.job_sources.telegram.contact import extract_contact
from src.job_sources.telegram.source import TelegramSource
from src.job_sources.telegram_control import HELP_TEXT as _TELEGRAM_HELP_TEXT
from src.job_sources.telegram_control import poll_control_commands
from src.job_sources.telegram_conversations import TelegramConversations
from src.job_sources.telegram_notify import (
    notify_from_secrets,
    send_notification,
)
from src.libs.resume_and_cover_builder import (
    ResumeFacade,
    ResumeGenerator,
    StyleManager,
)
from src.logging import logger
from src.resume_schemas.job_application_profile import JobApplicationProfile
from src.resume_schemas.resume import Resume
from src.scheduler import DEFAULT_INTERVAL_HOURS, Scheduler
from src.scheduler_state import load_state, record_run_result
from src.utils.chrome_utils import HTML_to_PDF, init_browser
from src.utils.constants import (
    PLAIN_TEXT_RESUME_YAML,
    RESUME_PDF,
    RESUME_PDF_LINKEDIN,
    SECRETS_YAML,
    WORK_PREFERENCES_YAML,
)


class ConfigError(Exception):
    """Отдельный тип исключения для ошибок конфигурации — чтобы
    main() мог поймать их отдельно от прочих сбоев и показать
    подсказку про гайд по настройке, а не голую трассировку."""

    pass


class ConfigValidator:
    """Проверяет config.yaml и secrets.yaml сразу при старте, чтобы
    некорректная настройка обнаружилась явной ошибкой, а не где-то
    в середине запроса к конкретному источнику вакансий."""

    EMAIL_REGEX = re.compile(
        r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    )
    REQUIRED_CONFIG_KEYS = {
        "remote": bool,
        "experience_level": dict,
        "job_types": dict,
        "date": dict,
        "positions": list,
        "locations": list,
        "location_blacklist": list,
        "distance": int,
        "company_blacklist": list,
        "title_blacklist": list,
    }
    EXPERIENCE_LEVELS = [
        "internship",
        "entry",
        "associate",
        "mid_senior_level",
        "director",
        "executive",
    ]
    JOB_TYPES = [
        "full_time",
        "contract",
        "part_time",
        "temporary",
        "internship",
        "other",
        "volunteer",
    ]
    DATE_FILTERS = ["all_time", "month", "week", "24_hours"]
    APPROVED_DISTANCES = {0, 5, 10, 25, 50, 100}

    @staticmethod
    def validate_email(email: str) -> bool:
        """Простая regex-проверка формата — этого достаточно, чтобы
        отсеять явный мусор, без отдельной библиотеки валидации."""
        return bool(ConfigValidator.EMAIL_REGEX.match(email))

    @staticmethod
    def load_yaml(yaml_path: Path) -> dict:
        """Оборачивает ошибки yaml и отсутствия файла в ConfigError,
        чтобы вся проверка конфигурации ловила один тип исключения
        с понятным текстом."""
        try:
            with open(yaml_path, "r") as stream:
                return yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            raise ConfigError(f"Error reading YAML file {yaml_path}: {exc}")
        except FileNotFoundError:
            raise ConfigError(f"YAML file not found: {yaml_path}")

    @classmethod
    def validate_config(cls, config_yaml_path: Path) -> dict:
        """Проверяет обязательные ключи config.yaml. Чёрные списки —
        единственное исключение: если ключ отсутствует или равен
        None, вместо ошибки подставляется пустой список, остальные
        поля обязательны."""
        parameters = cls.load_yaml(config_yaml_path)
        # Проверяем обязательные ключи и их типы
        for key, expected_type in cls.REQUIRED_CONFIG_KEYS.items():
            if key not in parameters:
                if key in [
                    "company_blacklist",
                    "title_blacklist",
                    "location_blacklist",
                ]:
                    parameters[key] = []
                else:
                    raise ConfigError(
                        f"Missing required key '{key}' in {config_yaml_path}"
                    )
            elif not isinstance(parameters[key], expected_type):
                if (
                    key
                    in [
                        "company_blacklist",
                        "title_blacklist",
                        "location_blacklist",
                    ]
                    and parameters[key] is None
                ):
                    parameters[key] = []
                else:
                    raise ConfigError(
                        f"Invalid type for key '{key}' in "
                        f"{config_yaml_path}. Expected "
                        f"{expected_type.__name__}."
                    )
        cls._validate_experience_levels(
            parameters["experience_level"], config_yaml_path
        )
        cls._validate_job_types(parameters["job_types"], config_yaml_path)
        cls._validate_date_filters(parameters["date"], config_yaml_path)
        cls._validate_list_of_strings(
            parameters, ["positions", "locations"], config_yaml_path
        )
        cls._validate_distance(parameters["distance"], config_yaml_path)
        cls._validate_blacklists(parameters, config_yaml_path)
        return parameters

    @classmethod
    def _validate_experience_levels(
        cls, experience_levels: dict, config_path: Path
    ):
        """Чтобы отсутствующее или небулево значение ("yes", 1) было
        явной ошибкой конфигурации, а не тихо проигнорированным
        фильтром."""
        for level in cls.EXPERIENCE_LEVELS:
            if not isinstance(experience_levels.get(level), bool):
                raise ConfigError(
                    f"Experience level '{level}' must be a boolean "
                    f"in {config_path}"
                )

    @classmethod
    def _validate_job_types(cls, job_types: dict, config_path: Path):
        """Та же защита, что и для experience_level — небулево
        значение должно падать явной ошибкой, а не молча пройти
        мимо фильтра."""
        for job_type in cls.JOB_TYPES:
            if not isinstance(job_types.get(job_type), bool):
                raise ConfigError(
                    f"Job type '{job_type}' must be a boolean in {config_path}"
                )

    @classmethod
    def _validate_date_filters(cls, date_filters: dict, config_path: Path):
        """Та же защита, что и для experience_level/job_types."""
        for date_filter in cls.DATE_FILTERS:
            if not isinstance(date_filters.get(date_filter), bool):
                raise ConfigError(
                    f"Date filter '{date_filter}' must be a boolean "
                    f"in {config_path}"
                )

    @classmethod
    def _validate_list_of_strings(
        cls, parameters: dict, keys: list, config_path: Path
    ):
        """positions/locations идут прямо в поисковые запросы
        источников — число или dict там сломает запрос куда менее
        понятной ошибкой, чем эта проверка."""
        for key in keys:
            if not all(isinstance(item, str) for item in parameters[key]):
                raise ConfigError(
                    f"'{key}' must be a list of strings in {config_path}"
                )

    @classmethod
    def _validate_distance(cls, distance: int, config_path: Path):
        """distance должен быть одним из значений, которые реально
        принимают фильтры источников — произвольное число просто
        молча даст пустую выдачу."""
        if distance not in cls.APPROVED_DISTANCES:
            raise ConfigError(
                f"Invalid distance value '{distance}' in "
                f"{config_path}. Must be one of: "
                f"{cls.APPROVED_DISTANCES}"
            )

    @classmethod
    def _validate_blacklists(cls, parameters: dict, config_path: Path):
        """Дополнительно превращает None в пустой список — в
        work_preferences.yaml эти поля часто оставляют пустыми."""
        for blacklist in [
            "company_blacklist",
            "title_blacklist",
            "location_blacklist",
        ]:
            if not isinstance(parameters.get(blacklist), list):
                raise ConfigError(
                    f"'{blacklist}' must be a list in {config_path}"
                )
            if parameters[blacklist] is None:
                parameters[blacklist] = []

    @staticmethod
    def validate_secrets(
        secrets_yaml_path: Path, provider: Optional[str] = None
    ) -> str:
        """Падает сразу, если ключа LLM нет или он пустой — вместо
        непонятного 401 где-то посреди прогона. provider (текущий
        активный провайдер — см. llm_provider.get_active_provider())
        — сначала ищет ключ в llm_api_keys.<provider> (дашборд:
        отдельный ключ на каждого провайдера), затем падает назад на
        общий llm_api_key (совместимость со старыми secrets.yaml,
        где был только один ключ)."""
        secrets = ConfigValidator.load_yaml(secrets_yaml_path)
        per_provider_key = (
            (secrets.get("llm_api_keys") or {}).get(provider)
            if provider
            else None
        )
        # Общий (старый) llm_api_key годится только как ключ для
        # LLM_MODEL_TYPE — того единственного провайдера, для
        # которого он и заводился раньше. Для любого другого
        # провайдера падать на него означало бы тихо слать чужой
        # (например OpenAI-) ключ в Groq/Gemini/DeepSeek API.
        legacy_applies = provider is None or provider == LLM_MODEL_TYPE
        key = per_provider_key or (
            secrets.get("llm_api_key") if legacy_applies else None
        )
        if not key:
            label = (
                f"llm_api_keys.{provider}' or 'llm_api_key"
                if provider
                else "llm_api_key"
            )
            raise ConfigError(
                f"Missing secret '{label}' in {secrets_yaml_path}"
            )
        return key


class FileManager:
    """Файловые операции и проверки вынесены отдельно от
    ConfigValidator, чтобы плохой YAML и отсутствующий файл давали
    разные, понятные причины падения."""

    REQUIRED_FILES = [
        SECRETS_YAML,
        WORK_PREFERENCES_YAML,
    ]

    @staticmethod
    def validate_data_folder(
        app_data_folder: Path,
    ) -> Tuple[Path, Path, Path, Path]:
        """Собирает сразу все недостающие файлы в одном сообщении,
        а не падает на первом же — чтобы не чинить data_folder по
        одному файлу за прогон. Заодно создаёт output/, если его
        ещё нет."""
        if not app_data_folder.is_dir():
            raise FileNotFoundError(
                f"Data folder not found: {app_data_folder}"
            )

        missing_files = [
            file
            for file in FileManager.REQUIRED_FILES
            if not (app_data_folder / file).exists()
        ]
        if missing_files:
            raise FileNotFoundError(
                f"Missing files in data folder: {', '.join(missing_files)}"
            )

        output_folder = app_data_folder / "output"
        output_folder.mkdir(exist_ok=True)

        return (
            app_data_folder / SECRETS_YAML,
            app_data_folder / WORK_PREFERENCES_YAML,
            app_data_folder / PLAIN_TEXT_RESUME_YAML,
            output_folder,
        )


def _project_root() -> Path:
    """В PyInstaller-сборке (desktop_app.spec) __file__ не указывает
    на реальную папку с забандленными datas — data_folder_example
    распаковывается во временный sys._MEIPASS, а не рядом с этим
    файлом. Из исходников (python main.py / python desktop_app.py)
    sys._MEIPASS не существует — используем расположение main.py."""
    meipass = getattr(sys, "_MEIPASS", None)
    return Path(meipass) if meipass else Path(__file__).resolve().parent


def bootstrap_data_folder(
    data_folder: Path, api_key: Optional[str] = None
) -> dict:
    """Чистая (без inquirer/print) логика создания data_folder из
    шаблона + запись llm_api_key — общая для CLI-визарда
    (run_setup_wizard) и веб-визарда (POST /api/setup/init в
    src/webui/api.py), чтобы не дублировать копирование шаблона в
    двух местах. Возвращает, что реально было сделано.

    Путь к шаблону — через _project_root(), а не текущую рабочую
    директорию: у веб-дашборда/десктоп-приложения (в т.ч. собранного
    PyInstaller-exe) CWD может быть чем угодно, в отличие от CLI,
    который всегда запускают из корня."""
    example = _project_root() / "data_folder_example"
    created_folder = not data_folder.exists()
    if created_folder:
        shutil.copytree(example, data_folder)
    else:
        for name in FileManager.REQUIRED_FILES:
            target = data_folder / name
            if not target.exists():
                shutil.copy(example / name, target)

    api_key_written = False
    if api_key:
        set_top_level_field(data_folder / SECRETS_YAML, "llm_api_key", api_key)
        api_key_written = True

    return {
        "created_folder": created_folder,
        "api_key_written": api_key_written,
    }


def run_setup_wizard(data_folder: Path) -> bool:
    """Гостевой мастер первого запуска — вызывается из main(), когда
    data_folder или secrets.yaml ещё не существуют. Спрашивает только
    критичный минимум (llm_api_key для OpenAI) — площадки/резюме/
    переключение на другого LLM-провайдера (правка LLM_MODEL_TYPE в
    config.py) пользователь заполняет вручную по docs/GUIDE.md:
    полный визард под все 8 площадок сразу и программная правка
    config.py — избыточны для одного захода и рискованны (Python-
    файл, не YAML). Возвращает False, если пользователь отказался —
    тогда main() останавливается, не пытаясь продолжить с неполным
    data_folder."""
    print("\nПохоже, это первый запуск — data_folder ещё не настроен.\n")
    if not inquirer.confirm(
        message=(
            "Создать data_folder из шаблона и задать API-ключ LLM " "сейчас?"
        ),
        default=True,
    ):
        print(
            "Ок. Вручную: скопируйте data_folder_example в data_folder "
            "и заполните secrets.yaml/work_preferences.yaml — см. "
            "docs/GUIDE.md."
        )
        return False

    api_key = inquirer.text(
        message=(
            "API-ключ OpenAI (llm_api_key) — Enter, чтобы пропустить и "
            "вписать позже вручную"
        )
    )
    result = bootstrap_data_folder(data_folder, api_key or None)
    if result["created_folder"]:
        print(f"Создано: {data_folder}/ (копия data_folder_example/)")
    if result["api_key_written"]:
        print("llm_api_key записан в data_folder/secrets.yaml.")
    else:
        print(
            "Пропущено — впишите llm_api_key в "
            "data_folder/secrets.yaml вручную."
        )

    print(
        "\nДалее вручную (подробности — docs/GUIDE.md):\n"
        "  1. Положите резюме как data_folder/resume.pdf\n"
        "  2. В data_folder/work_preferences.yaml укажите позиции/"
        "локации\n"
        "  3. Заполните ключи нужных площадок в "
        "data_folder/secrets.yaml\n"
        "  4. Если провайдер LLM не OpenAI — поменяйте "
        "LLM_MODEL_TYPE/LLM_MODEL в config.py\n"
    )
    return True


def ensure_plain_text_resume(parameters: dict, llm_api_key: str) -> Path:
    """plain_text_resume.yaml нужен только трём старым пунктам меню
    (Generate Resume*), поэтому не блокирует запуск всего приложения
    (см. FileManager.REQUIRED_FILES) — генерируется через LLM из
    resume.pdf лениво, при первом обращении к одному из этих
    пунктов, и переиспользуется дальше без повторной генерации."""
    plain_text_resume_file: Path = parameters["plainTextResumeFile"]
    if not plain_text_resume_file.exists():
        resume_pdf_path = parameters["dataFolder"] / RESUME_PDF
        if not resume_pdf_path.exists():
            raise FileNotFoundError(
                f"Neither {plain_text_resume_file} nor {resume_pdf_path} "
                "found — need at least one to generate a resume."
            )
        logger.info(
            f"{plain_text_resume_file} not found — extracting it from "
            f"{resume_pdf_path} via LLM."
        )
        plain_text_resume_file.write_text(
            extract_plain_text_resume(resume_pdf_path, llm_api_key),
            encoding="utf-8",
        )
    return plain_text_resume_file


def force_refresh_plain_text_resume(
    parameters: dict, llm_api_key: str
) -> Path:
    """В отличие от ensure_plain_text_resume — перегенерирует
    plain_text_resume.yaml из resume.pdf, даже если файл уже есть.
    Нужна, когда пользователь заменил resume.pdf: без этого
    закэшированный текст остаётся старым, пока кто-то вручную не
    удалит plain_text_resume.yaml (дашборд: кнопка "Обновить из PDF"
    на панели генерации резюме)."""
    plain_text_resume_file: Path = parameters["plainTextResumeFile"]
    resume_pdf_path: Path = parameters["dataFolder"] / RESUME_PDF
    if not resume_pdf_path.exists():
        raise FileNotFoundError(
            f"Resume PDF not found: {resume_pdf_path}. Place your "
            f"resume as '{RESUME_PDF}' in {parameters['dataFolder']}."
        )
    plain_text_resume_file.write_text(
        extract_plain_text_resume(resume_pdf_path, llm_api_key),
        encoding="utf-8",
    )
    return plain_text_resume_file


def generate_positions_from_resume(
    parameters: dict, llm_api_key: str
) -> list[str]:
    """Кнопка "Сгенерировать из резюме" на дашборде — та же логика,
    что автовывод positions при пустом work_preferences.yaml на
    старте CLI (см. main()), но по явному запросу и с возвратом
    результата вызывающему, а не немым присвоением в config."""
    resume_pdf_path: Path = parameters["dataFolder"] / RESUME_PDF
    if not resume_pdf_path.exists():
        raise FileNotFoundError(
            f"Resume PDF not found: {resume_pdf_path}. Place your "
            f"resume as '{RESUME_PDF}' in {parameters['dataFolder']}."
        )
    return infer_positions_from_resume(resume_pdf_path, llm_api_key)


def create_cover_letter(
    parameters: dict,
    llm_api_key: str,
    style_name: Optional[str] = None,
    job_url: Optional[str] = None,
) -> Optional[Path]:
    """
    Ручной прогон по одной вставленной ссылке на вакансию — через
    старый ResumeFacade+Selenium, а не через
    LLM-конвейер score_job_fit/generate_cover_letter_for_job,
    которым пользуются функции search_and_apply_*.

    style_name/job_url заданы явно — используются как есть (вызов из
    веб-дашборда, где спрашивать через терминал нельзя); не заданы —
    как раньше, спрашивает через inquirer в консоли.
    """
    try:
        logger.info("Generating a CV based on provided parameters.")

        # Загружаем резюме в виде обычного текста
        plain_text_resume_file = ensure_plain_text_resume(
            parameters, llm_api_key
        )
        with open(plain_text_resume_file, "r", encoding="utf-8") as file:
            plain_text_resume = file.read()

        style_manager = StyleManager()
        available_styles = style_manager.get_styles()

        if not available_styles:
            logger.warning(
                "No styles available. Proceeding without style selection."
            )
        elif style_name:
            style_manager.set_selected_style(style_name)
        else:
            # Предлагаем пользователю выбрать стиль
            choices = style_manager.format_choices(available_styles)
            questions = [
                inquirer.List(
                    "style",
                    message="Select a style for the resume:",
                    choices=choices,
                )
            ]
            style_answer = inquirer.prompt(questions)
            if style_answer and "style" in style_answer:
                selected_choice = style_answer["style"]
                for name, (
                    file_name,
                    author_link,
                ) in available_styles.items():
                    if selected_choice.startswith(name):
                        style_manager.set_selected_style(name)
                        logger.info(f"Selected style: {name}")
                        break
            else:
                logger.warning(
                    "No style selected. Proceeding with default style."
                )
        if not job_url:
            questions = [
                inquirer.Text(
                    "job_url",
                    message="Please enter the URL of the job description:",
                )
            ]
            answers = inquirer.prompt(questions)
            job_url = answers.get("job_url")
        resume_generator = ResumeGenerator()
        resume_object = Resume(plain_text_resume)
        driver = init_browser()
        resume_generator.set_resume_object(resume_object)
        resume_facade = ResumeFacade(
            api_key=llm_api_key,
            style_manager=style_manager,
            resume_generator=resume_generator,
            resume_object=resume_object,
            output_path=Path(parameters["outputFileDirectory"]),
        )
        resume_facade.set_driver(driver)
        resume_facade.link_to_job(job_url)
        result_base64, suggested_name = resume_facade.create_cover_letter()

        # Декодируем Base64 в бинарные данные
        try:
            pdf_data = base64.b64decode(result_base64)
        except binascii.Error as e:
            logger.error("Error decoding Base64: %s", e)
            raise

        # Определяем путь к папке для вывода, используя
        # suggested_name
        output_dir = Path(parameters["outputFileDirectory"]) / suggested_name

        # Создаём папку, если её ещё нет
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            logger.info(
                f"Cartella di output creata o già esistente: {output_dir}"
            )
        except IOError as e:
            logger.error("Error creating output directory: %s", e)
            raise

        output_path = output_dir / "cover_letter_tailored.pdf"
        try:
            with open(output_path, "wb") as file:
                file.write(pdf_data)
            logger.info(f"CV salvato in: {output_path}")
        except IOError as e:
            logger.error("Error writing file: %s", e)
            raise
        return output_path
    except Exception as e:
        logger.exception(f"An error occurred while creating the CV: {e}")
        raise


def create_resume_pdf_job_tailored(
    parameters: dict,
    llm_api_key: str,
    style_name: Optional[str] = None,
    job_url: Optional[str] = None,
) -> Optional[Path]:
    """
    То же самое, что create_cover_letter, но результат —
    резюме под конкретную вакансию, а не сопроводительное письмо.
    """
    try:
        logger.info("Generating a CV based on provided parameters.")

        # Загружаем резюме в виде обычного текста
        plain_text_resume_file = ensure_plain_text_resume(
            parameters, llm_api_key
        )
        with open(plain_text_resume_file, "r", encoding="utf-8") as file:
            plain_text_resume = file.read()

        style_manager = StyleManager()
        available_styles = style_manager.get_styles()

        if not available_styles:
            logger.warning(
                "No styles available. Proceeding without style selection."
            )
        elif style_name:
            style_manager.set_selected_style(style_name)
        else:
            # Предлагаем пользователю выбрать стиль
            choices = style_manager.format_choices(available_styles)
            questions = [
                inquirer.List(
                    "style",
                    message="Select a style for the resume:",
                    choices=choices,
                )
            ]
            style_answer = inquirer.prompt(questions)
            if style_answer and "style" in style_answer:
                selected_choice = style_answer["style"]
                for name, (
                    file_name,
                    author_link,
                ) in available_styles.items():
                    if selected_choice.startswith(name):
                        style_manager.set_selected_style(name)
                        logger.info(f"Selected style: {name}")
                        break
            else:
                logger.warning(
                    "No style selected. Proceeding with default style."
                )
        if not job_url:
            questions = [
                inquirer.Text(
                    "job_url",
                    message="Please enter the URL of the job description:",
                )
            ]
            answers = inquirer.prompt(questions)
            job_url = answers.get("job_url")
        resume_generator = ResumeGenerator()
        resume_object = Resume(plain_text_resume)
        driver = init_browser()
        resume_generator.set_resume_object(resume_object)
        resume_facade = ResumeFacade(
            api_key=llm_api_key,
            style_manager=style_manager,
            resume_generator=resume_generator,
            resume_object=resume_object,
            output_path=Path(parameters["outputFileDirectory"]),
        )
        resume_facade.set_driver(driver)
        resume_facade.link_to_job(job_url)
        result_base64, suggested_name = (
            resume_facade.create_resume_pdf_job_tailored()
        )

        # Декодируем Base64 в бинарные данные
        try:
            pdf_data = base64.b64decode(result_base64)
        except binascii.Error as e:
            logger.error("Error decoding Base64: %s", e)
            raise

        # Определяем путь к папке для вывода, используя
        # suggested_name
        output_dir = Path(parameters["outputFileDirectory"]) / suggested_name

        # Создаём папку, если её ещё нет
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            logger.info(
                f"Cartella di output creata o già esistente: {output_dir}"
            )
        except IOError as e:
            logger.error("Error creating output directory: %s", e)
            raise

        output_path = output_dir / "resume_tailored.pdf"
        try:
            with open(output_path, "wb") as file:
                file.write(pdf_data)
            logger.info(f"CV salvato in: {output_path}")
        except IOError as e:
            logger.error("Error writing file: %s", e)
            raise
        return output_path
    except Exception as e:
        logger.exception(f"An error occurred while creating the CV: {e}")
        raise


def create_resume_pdf(
    parameters: dict,
    llm_api_key: str,
    style_name: Optional[str] = None,
) -> Optional[Path]:
    """
    Базовое резюме без привязки к вакансии — тот же
    ResumeFacade+Selenium, но без job_url и без обращения к LLM
    за подгонкой под конкретное описание.
    """
    try:
        logger.info("Generating a CV based on provided parameters.")

        # Загружаем резюме в виде обычного текста
        plain_text_resume_file = ensure_plain_text_resume(
            parameters, llm_api_key
        )
        with open(plain_text_resume_file, "r", encoding="utf-8") as file:
            plain_text_resume = file.read()

        # Инициализируем StyleManager
        style_manager = StyleManager()
        available_styles = style_manager.get_styles()

        if not available_styles:
            logger.warning(
                "No styles available. Proceeding without style selection."
            )
        elif style_name:
            style_manager.set_selected_style(style_name)
        else:
            # Предлагаем пользователю выбрать стиль
            choices = style_manager.format_choices(available_styles)
            questions = [
                inquirer.List(
                    "style",
                    message="Select a style for the resume:",
                    choices=choices,
                )
            ]
            style_answer = inquirer.prompt(questions)
            if style_answer and "style" in style_answer:
                selected_choice = style_answer["style"]
                for name, (
                    file_name,
                    author_link,
                ) in available_styles.items():
                    if selected_choice.startswith(name):
                        style_manager.set_selected_style(name)
                        logger.info(f"Selected style: {name}")
                        break
            else:
                logger.warning(
                    "No style selected. Proceeding with default style."
                )

        # Инициализируем генератор резюме
        resume_generator = ResumeGenerator()
        resume_object = Resume(plain_text_resume)
        driver = init_browser()
        resume_generator.set_resume_object(resume_object)

        # Создаём ResumeFacade
        resume_facade = ResumeFacade(
            api_key=llm_api_key,
            style_manager=style_manager,
            resume_generator=resume_generator,
            resume_object=resume_object,
            output_path=Path(parameters["outputFileDirectory"]),
        )
        resume_facade.set_driver(driver)
        result_base64 = resume_facade.create_resume_pdf()

        # Декодируем Base64 в бинарные данные
        try:
            pdf_data = base64.b64decode(result_base64)
        except binascii.Error as e:
            logger.error("Error decoding Base64: %s", e)
            raise

        # Определяем папку для вывода
        output_dir = Path(parameters["outputFileDirectory"])

        # Записываем PDF-файл
        output_path = output_dir / "resume_base.pdf"
        try:
            with open(output_path, "wb") as file:
                file.write(pdf_data)
            logger.info(f"Resume saved at: {output_path}")
        except IOError as e:
            logger.error("Error writing file: %s", e)
            raise
        return output_path
    except Exception as e:
        logger.exception(f"An error occurred while creating the CV: {e}")
        raise


def apply_llm_provider_override(parameters: dict) -> None:
    """Читает опциональный блок llm: в work_preferences.yaml
    (дашборд — иконки провайдера в настройках) и прокидывает его в
    llm_provider.set_provider_override(), чтобы все 8 мест, что зовут
    get_chat_llm(), забрали новый провайдер без перезапуска процесса.
    llm: отсутствует или пуст — override сбрасывается (провайдер по
    умолчанию — config.LLM_MODEL_TYPE), а не остаётся зависшим от
    предыдущего вызова. llm.mode — free/paid/auto, см.
    llm_provider.set_fallback_mode(). llm.fallback_enabled — False
    запрещает переключение на других настроенных провайдеров при
    ошибке/лимите (строго один выбранный провайдер), см.
    llm_provider.set_fallback_enabled()."""
    llm_config = parameters.get("llm") or {}
    set_llm_provider_override(
        llm_config.get("provider"),
        llm_config.get("model"),
        llm_config.get("base_url"),
    )
    set_llm_fallback_mode(llm_config.get("mode"))
    set_llm_fallback_enabled(llm_config.get("fallback_enabled"))


def _job_min_score(parameters: dict) -> float:
    """Порог отсева (score_job_fit ниже — сразу skipped_low_fit, письмо
    не генерируется). Приоритет: limits.job_min_score (дашборд —
    панель "Лимиты") > config.JOB_MIN_SCORE."""
    return float(
        (parameters.get("limits") or {}).get("job_min_score", JOB_MIN_SCORE)
    )


def _job_suitability_score(parameters: dict) -> float:
    """Порог "уверенного" фита — между job_min_score и этим значением
    отклик всё равно уходит, но помечается как weak и логируется
    отдельно (см. main.classify_fit). Приоритет: тот же, что
    _job_min_score."""
    return float(
        (parameters.get("limits") or {}).get(
            "job_suitability_score", JOB_SUITABILITY_SCORE
        )
    )


def _daily_limit(parameters: dict, source: Optional[str] = None) -> int:
    """Дневной лимит откликов. Приоритет: daily_application_limit
    внутри блока конкретной площадки (headhunter:/superjob:/...,
    дашборд — колонка "Дневной лимит" в таблице настроек) >
    глобальный дефолт (для LinkedIn —
    limits.linkedin_daily_application_limit, для остальных —
    limits.daily_application_limit, дашборд — панель "Лимиты
    откликов") > соответствующая константа в config.py."""
    if source:
        source_config = parameters.get(source) or {}
        if "daily_application_limit" in source_config:
            return int(source_config["daily_application_limit"])
    if source == "linkedin":
        return int(
            (parameters.get("limits") or {}).get(
                "linkedin_daily_application_limit",
                LINKEDIN_DAILY_APPLICATION_LIMIT,
            )
        )
    return int(
        (parameters.get("limits") or {}).get(
            "daily_application_limit", DAILY_APPLICATION_LIMIT
        )
    )


def _linkedin_daily_limit(parameters: dict) -> int:
    """Тонкая обёртка над _daily_limit(parameters, "linkedin") — для
    мест, которые явно про LinkedIn (дашборд: /api/status)."""
    return _daily_limit(parameters, "linkedin")


def _total_daily_limit(parameters: dict) -> Optional[int]:
    """Общий лимит откликов в сутки — единый бюджет на ВСЕ площадки
    вместе, а не независимый лимит на каждую (см. _daily_limit() —
    тот применяется per-площадка). limits.total_daily_application_
    limit не задан или 0 — функция выключена (обратная
    совместимость: без этого поля в work_preferences.yaml поведение
    не меняется, площадки по-прежнему считают свой лимит
    независимо)."""
    value = (parameters.get("limits") or {}).get(
        "total_daily_application_limit"
    )
    return int(value) if value else None


def _total_daily_limit_reached(
    parameters: dict, applied_log: AppliedLog
) -> bool:
    """True — общий (across all площадок) дневной бюджет откликов
    исчерпан, вызывающий цикл должен остановиться немедленно, даже
    если у своей площадки лимит ещё не исчерпан. Вызывается в каждом
    search_and_apply_*/search_* так же, как уже существующая
    проверка per-площадочного daily_limit — тем же местом в цикле."""
    total_limit = _total_daily_limit(parameters)
    if total_limit is None:
        return False
    if applied_log.applied_today_count_all() >= total_limit:
        logger.info(
            f"Reached total daily application limit ({total_limit}) "
            "across all platforms combined."
        )
        notify(
            parameters,
            f"Общий дневной лимит откликов ({total_limit}) на все "
            "площадки вместе достигнут.",
        )
        return True
    return False


def _job_max_applications(
    parameters: dict, source: Optional[str] = None
) -> int:
    """Лимит откликов за один прогон. Приоритет: job_max_applications
    внутри блока конкретной площадки (headhunter:/superjob:/...,
    дашборд — колонка "Откликов за прогон" в таблице настроек) >
    limits.job_max_applications (общий дефолт, дашборд — панель
    "Лимиты откликов") > config.JOB_MAX_APPLICATIONS."""
    if source:
        source_config = parameters.get(source) or {}
        if "job_max_applications" in source_config:
            return int(source_config["job_max_applications"])
    return int(
        (parameters.get("limits") or {}).get(
            "job_max_applications", JOB_MAX_APPLICATIONS
        )
    )


def _resolve_resume_id(
    client, configured_resume_id: Optional[str], platform_label: str
) -> str:
    """resume_id необязательно вписывать вручную — резюме уже лежит
    на самой площадке (пользователь загрузил его туда сам через её
    сайт), поэтому вместо немедленного отказа сначала смотрим список
    резюме через API площадки (client.list_resumes()): одно найдено —
    используем его, несколько — просим выбрать явно (со списком id,
    чтобы не гадать по URL), ни одного — площадка правда пуста,
    сначала нужно загрузить резюме на её сайте вручную. Локальный
    resume.pdf тут не подставить — у официального API HH/SuperJob
    нет метода "откликнуться файлом", только по id уже
    существующего на площадке резюме."""
    if configured_resume_id:
        return configured_resume_id
    resumes = client.list_resumes()
    if len(resumes) == 1:
        resume_id = resumes[0]["id"]
        logger.info(
            f"{platform_label}.resume_id не указан — использую "
            f"единственное найденное резюме на площадке: {resume_id}"
        )
        return resume_id
    if not resumes:
        raise ConfigError(
            f"{platform_label}.resume_id не задан, и на площадке не "
            "найдено ни одного резюме — сначала загрузите резюме на "
            "сайте площадки, потом впишите его id в "
            "work_preferences.yaml."
        )
    ids = ", ".join(r["id"] for r in resumes)
    raise ConfigError(
        f"{platform_label}.resume_id не задан, а на площадке "
        f"несколько резюме — впишите нужный id в work_preferences.yaml "
        f"(один из: {ids})"
    )


def search_and_apply_headhunter(parameters: dict, llm_api_key: str):
    """
    Ищет на HeadHunter вакансии по work_preferences.yaml через
    настоящую браузерную сессию hh.ru (вход по номеру телефона + SMS —
    см. HeadHunterSession, официальный OAuth API требует регистрации
    отдельного приложения, которое HH одобряет не сразу и не
    гарантированно), пишет под каждую подходящую вакансию персональное
    сопроводительное письмо на основе data_folder/resume.pdf и либо
    откликается кликом (при headhunter.auto_apply: true), либо просто
    логирует и записывает как dry-run. Поиск всегда идёт по всей
    России без фильтра по городу (area=113 в HeadHunterBrowserClient) —
    кандидат работает удалённо, конкретный регион не нужен.
    """
    data_folder: Path = parameters["dataFolder"]
    resume_pdf_path = data_folder / RESUME_PDF
    if not resume_pdf_path.exists():
        raise FileNotFoundError(
            f"Resume PDF not found: {resume_pdf_path}. Place your "
            f"resume as '{RESUME_PDF}' in {data_folder}."
        )

    hh_preferences = parameters.get("headhunter") or {}
    auto_apply = bool(hh_preferences.get("auto_apply", False))

    output_folder: Path = parameters["outputFileDirectory"]
    profile_dir = output_folder / ".chrome_profile_headhunter"
    applied_log = AppliedLog(output_folder / "applied_log.json")

    if is_still_blocked(output_folder, "headhunter"):
        logger.warning("hh.ru is cooling down after a block — skipping.")
        return

    HeadHunterSession(profile_dir).ensure_logged_in()

    with HeadHunterBrowserClient(profile_dir) as client:

        # ponytail: opt-in, как auto_apply/auto_reply — см. docstring
        # HeadHunterBrowserClient.bump_resume про непроверенный селектор.
        # Best-effort: сбой поднятия резюме не должен останавливать поиск
        # и отклики ниже.
        if hh_preferences.get("auto_bump_resume") and hh_preferences.get(
            "resume_id"
        ):
            try:
                bumped = client.bump_resume(hh_preferences["resume_id"])
                logger.info(
                    "Резюме поднято в поиске HH."
                    if bumped
                    else "Поднять резюме пока нельзя (недавно уже поднимали) "
                    "или кнопка не найдена."
                )
            except Exception as e:
                logger.warning(f"Не удалось поднять резюме на HH: {e}")

        source: JobSource = HeadHunterBrowserSource(client)
        try:
            jobs = source.search(parameters)
        except PlatformBlockedError as e:
            logger.error(f"hh.ru appears to have blocked us: {e}")
            mark_blocked(output_folder, "headhunter")
            notify(
                parameters,
                f"hh.ru: похоже на блокировку ({e}). "
                "Площадка поставлена на паузу на 24ч.",
            )
            return
        logger.info(f"Found {len(jobs)} matching HeadHunter vacancies.")

        daily_limit = randomized_daily_limit(
            _daily_limit(parameters, "headhunter")
        )
        sent_count = 0
        job_max_applications = _job_max_applications(parameters, "headhunter")
        for job in jobs:
            if sent_count >= job_max_applications:
                logger.info(
                    f"Reached JOB_MAX_APPLICATIONS "
                    f"({job_max_applications}) for this run."
                )
                break
            if _total_daily_limit_reached(parameters, applied_log):
                break
            if applied_log.already_applied(job):
                continue
            if (
                auto_apply
                and parameters.get("apply_once_at_company")
                and applied_log.already_applied_to_company(job)
            ):
                logger.info(
                    f"Skipping {job.company} - already applied there "
                    f"(apply_once_at_company)."
                )
                continue
            if (
                auto_apply
                and applied_log.applied_today_count(job.source) >= daily_limit
            ):
                logger.info(
                    f"Reached daily application limit "
                    f"({daily_limit}) for {job.source} today."
                )
                notify(
                    parameters,
                    f"Дневной лимит откликов ({daily_limit}) достигнут "
                    f"для {job.source}.",
                )
                break

            fit = score_job_fit(resume_pdf_path, job, llm_api_key)
            tier = classify_fit(
                fit.score,
                _job_min_score(parameters),
                _job_suitability_score(parameters),
            )
            if tier == "skip":
                logger.info(
                    f"Skipping {job.role} at {job.company}: fit score "
                    f"{fit.score}/10 below minimum."
                )
                applied_log.record(
                    job, "", "", "skipped_low_fit", fit.score, fit.gaps
                )
                continue
            if tier == "weak":
                logger.info(
                    f"{job.role} at {job.company}: weak fit "
                    f"({fit.score}/10, gaps: {', '.join(fit.gaps)})."
                )

            if auto_apply:
                wait_before_apply()

                def _cover_letter_fn() -> str:
                    return generate_cover_letter_for_job(
                        resume_pdf_path, job, llm_api_key
                    )

                def _ai_answer_fn(question_text: str) -> str:
                    # Переиспользуем ту же генерацию, что и у автоответов
                    # в чате (reply_answerer.py) — вопрос теста вакансии
                    # семантически то же самое, что "сообщение работодателя,
                    # на которое нужно кратко ответить от лица кандидата".
                    return generate_reply(
                        resume_pdf_path,
                        question_text,
                        job.role,
                        job.company,
                        build_preferences_summary(parameters),
                        llm_api_key,
                    )

                try:
                    applied, cover_letter = client.apply(
                        job.link, _cover_letter_fn, _ai_answer_fn
                    )
                except PlatformBlockedError as e:
                    # ponytail: раньше это ловилось общим except ниже и
                    # просто continue'ило на следующую вакансию — бот
                    # долбил driver.get() по всем оставшимся вакансиям в
                    # уже заблокированной сессии вместо остановки (см.
                    # инцидент — капча на HH, бот продолжал обновлять
                    # сайт). Как и в блоке search() выше — сразу
                    # mark_blocked и стоп для этого прогона.
                    logger.error(f"hh.ru appears to have blocked us: {e}")
                    mark_blocked(output_folder, "headhunter")
                    notify(
                        parameters,
                        f"hh.ru: похоже на блокировку ({e}). "
                        "Площадка поставлена на паузу на 24ч.",
                    )
                    break
                except Exception as e:
                    logger.exception(
                        "Failed to apply/generate cover letter for "
                        f"{job.role} at {job.company}, skipping this "
                        f"vacancy: {e}"
                    )
                    continue
                if applied:
                    status: Literal["applied", "dry_run"] = "applied"
                    logger.info(
                        f"Applied to {job.role} at {job.company} ({job.link})"
                    )
                else:
                    status = "dry_run"
                    logger.warning(
                        "Кнопка 'Откликнуться' не найдена на "
                        f"{job.link} — записано как dry-run."
                    )
            else:
                try:
                    cover_letter = generate_cover_letter_for_job(
                        resume_pdf_path, job, llm_api_key
                    )
                except Exception as e:
                    logger.exception(
                        f"Failed to generate cover letter for {job.role} at "
                        f"{job.company}, skipping this vacancy: {e}"
                    )
                    continue
                status = "dry_run"
                logger.info(
                    f"[dry run] Would apply to {job.role} at {job.company} "
                    f"({job.link})"
                )

            applied_log.record(
                job, cover_letter, "", status, fit.score, fit.gaps
            )
            sent_count += 1


def search_and_apply_superjob(parameters: dict, llm_api_key: str):
    """
    Ищет на SuperJob вакансии по work_preferences.yaml, пишет
    под каждую персональное сопроводительное письмо на основе
    data_folder/resume.pdf и либо откликается (при
    superjob.auto_apply: true), либо просто логирует и
    записывает как dry-run.
    """
    data_folder: Path = parameters["dataFolder"]
    resume_pdf_path = data_folder / RESUME_PDF
    if not resume_pdf_path.exists():
        raise FileNotFoundError(
            f"Resume PDF not found: {resume_pdf_path}. Place your "
            f"resume as '{RESUME_PDF}' in {data_folder}."
        )

    secrets = ConfigValidator.load_yaml(parameters["secretsFile"])
    sj_secrets = secrets.get("superjob") or {}
    client_id = sj_secrets.get("client_id")
    client_secret = sj_secrets.get("client_secret")
    if not client_id or not client_secret:
        raise ConfigError(
            "Missing superjob.client_id/client_secret in secrets.yaml"
        )

    sj_preferences = parameters.get("superjob") or {}
    auto_apply = bool(sj_preferences.get("auto_apply", False))
    resume_id = sj_preferences.get("resume_id")

    output_folder: Path = parameters["outputFileDirectory"]
    auth = SuperJobAuth(
        client_id, client_secret, output_folder / ".superjob_token.json"
    )
    client = SuperJobClient(auth.get_access_token(), client_secret)
    if auto_apply:
        resume_id = _resolve_resume_id(client, resume_id, "superjob")
    applied_log = AppliedLog(output_folder / "applied_log.json")

    source: JobSource = SuperJobSource(client)
    jobs = source.search(parameters)
    logger.info(f"Found {len(jobs)} matching SuperJob vacancies.")

    daily_limit = randomized_daily_limit(_daily_limit(parameters, "superjob"))
    sent_count = 0
    job_max_applications = _job_max_applications(parameters, "superjob")
    for job in jobs:
        if sent_count >= job_max_applications:
            logger.info(
                f"Reached JOB_MAX_APPLICATIONS "
                f"({job_max_applications}) for this run."
            )
            break
        if _total_daily_limit_reached(parameters, applied_log):
            break
        if applied_log.already_applied(job):
            continue
        if (
            auto_apply
            and parameters.get("apply_once_at_company")
            and applied_log.already_applied_to_company(job)
        ):
            logger.info(
                f"Skipping {job.company} - already applied there "
                f"(apply_once_at_company)."
            )
            continue
        if (
            auto_apply
            and applied_log.applied_today_count(job.source) >= daily_limit
        ):
            logger.info(
                f"Reached daily application limit "
                f"({daily_limit}) for {job.source} today."
            )
            notify(
                parameters,
                f"Дневной лимит откликов ({daily_limit}) достигнут "
                f"для {job.source}.",
            )
            break

        fit = score_job_fit(resume_pdf_path, job, llm_api_key)
        tier = classify_fit(
            fit.score,
            _job_min_score(parameters),
            _job_suitability_score(parameters),
        )
        if tier == "skip":
            logger.info(
                f"Skipping {job.role} at {job.company}: fit score "
                f"{fit.score}/10 below minimum."
            )
            applied_log.record(
                job, "", "", "skipped_low_fit", fit.score, fit.gaps
            )
            continue
        if tier == "weak":
            logger.info(
                f"{job.role} at {job.company}: weak fit "
                f"({fit.score}/10, gaps: {', '.join(fit.gaps)})."
            )

        try:
            cover_letter = generate_cover_letter_for_job(
                resume_pdf_path, job, llm_api_key
            )
        except Exception as e:
            logger.exception(
                f"Failed to generate cover letter for {job.role} at "
                f"{job.company}, skipping this vacancy: {e}"
            )
            continue

        if auto_apply:
            wait_before_apply()
            client.apply(resume_id or "", job.external_id, cover_letter)
            status: Literal["applied", "dry_run"] = "applied"
            logger.info(f"Applied to {job.role} at {job.company} ({job.link})")
        else:
            status = "dry_run"
            logger.info(
                f"[dry run] Would apply to {job.role} at {job.company} "
                f"({job.link})"
            )

        applied_log.record(
            job, cover_letter, resume_id or "", status, fit.score, fit.gaps
        )
        sent_count += 1


def search_geekjob(parameters: dict, llm_api_key: str):
    """
    Ищет на geekjob.ru вакансии по work_preferences.yaml. Если
    geekjob.auto_apply — true, откликается кликом на кнопку
    "Откликнуться" на странице вакансии — best-effort, НЕ проверено
    на живом залогиненном аккаунте (вход у geekjob.ru только через
    OAuth соцсетей, пароль пользователя здесь никогда не вводится,
    см. GeekjobSession), в отличие от HH/GetMatch. Если кнопка не
    найдётся — тихо считается dry-run, ничего не падает. Иначе — как
    раньше, каждое совпадение просто пишется как dry-run.
    """
    data_folder: Path = parameters["dataFolder"]
    resume_pdf_path = data_folder / RESUME_PDF
    if not resume_pdf_path.exists():
        raise FileNotFoundError(
            f"Resume PDF not found: {resume_pdf_path}. Place your "
            f"resume as '{RESUME_PDF}' in {data_folder}."
        )

    gj_preferences = parameters.get("geekjob") or {}
    auto_apply = bool(gj_preferences.get("auto_apply", False))

    output_folder: Path = parameters["outputFileDirectory"]
    applied_log = AppliedLog(output_folder / "applied_log.json")

    if is_still_blocked(output_folder, "geekjob"):
        logger.warning("geekjob.ru is cooling down after a block — skipping.")
        return

    profile_dir = output_folder / ".chrome_profile_geekjob"

    # Вход — до поиска, а не после: если auto_apply включён, всё равно
    # придётся логиниться, чтобы откликаться — лучше сразу запросить
    # вход (быстро), чем заставлять ждать несколько минут поиска ради
    # окна логина в конце.
    if auto_apply:
        GeekjobSession(profile_dir).ensure_logged_in()

    client = GeekjobClient(profile_dir)
    source: JobSource = GeekjobSource(client)
    try:
        with client:
            jobs = source.search(parameters)
    except PlatformBlockedError as e:
        logger.error(f"geekjob.ru appears to have blocked us: {e}")
        mark_blocked(output_folder, "geekjob")
        notify(
            parameters,
            f"geekjob.ru: похоже на блокировку ({e}). "
            "Площадка поставлена на паузу на 24ч.",
        )
        return
    logger.info(f"Found {len(jobs)} matching geekjob.ru vacancies.")

    sent_count = 0
    job_max_applications = _job_max_applications(parameters, "geekjob")
    for job in jobs:
        if sent_count >= job_max_applications:
            logger.info(
                f"Reached JOB_MAX_APPLICATIONS "
                f"({job_max_applications}) for this run."
            )
            break
        if _total_daily_limit_reached(parameters, applied_log):
            break
        if applied_log.already_applied(job):
            continue

        fit = score_job_fit(resume_pdf_path, job, llm_api_key)
        tier = classify_fit(
            fit.score,
            _job_min_score(parameters),
            _job_suitability_score(parameters),
        )
        if tier == "skip":
            logger.info(
                f"Skipping {job.role} at {job.company}: fit score "
                f"{fit.score}/10 below minimum."
            )
            applied_log.record(
                job, "", "", "skipped_low_fit", fit.score, fit.gaps
            )
            continue
        if tier == "weak":
            logger.info(
                f"{job.role} at {job.company}: weak fit "
                f"({fit.score}/10, gaps: {', '.join(fit.gaps)})."
            )

        try:
            cover_letter = generate_cover_letter_for_job(
                resume_pdf_path, job, llm_api_key
            )
        except Exception as e:
            logger.exception(
                f"Failed to generate cover letter for {job.role} at "
                f"{job.company}, skipping this vacancy: {e}"
            )
            continue

        if auto_apply:
            applied = client.apply(job.link, profile_dir)
            if applied:
                status: Literal["applied", "dry_run"] = "applied"
                logger.info(
                    f"Applied to {job.role} at {job.company} ({job.link})"
                )
            else:
                status = "dry_run"
                logger.warning(
                    "Кнопка 'Откликнуться' не найдена на "
                    f"{job.link} — записано как dry-run."
                )
        else:
            status = "dry_run"
            logger.info(
                f"[manual apply needed] {job.role} at {job.company} "
                f"({job.link})"
            )

        applied_log.record(
            job,
            cover_letter,
            resume_id="",
            status=status,
            score=fit.score,
            gaps=fit.gaps,
        )
        sent_count += 1


def search_rabota_ru(parameters: dict, llm_api_key: str):
    """
    Ищет на rabota.ru вакансии по work_preferences.yaml. Если
    rabota_ru.auto_apply — true, откликается кликом на кнопку
    "Откликнуться" на странице вакансии — best-effort, НЕ проверено
    на живом залогиненном аккаунте (вход у rabota.ru только через
    OAuth/код, пароль пользователя здесь никогда не вводится, см.
    RabotaRuSession), в отличие от HH/GetMatch. Если кнопка не
    найдётся — тихо считается dry-run, ничего не падает. Иначе — как
    раньше, каждое совпадение просто пишется как dry-run.
    """
    data_folder: Path = parameters["dataFolder"]
    resume_pdf_path = data_folder / RESUME_PDF
    if not resume_pdf_path.exists():
        raise FileNotFoundError(
            f"Resume PDF not found: {resume_pdf_path}. Place your "
            f"resume as '{RESUME_PDF}' in {data_folder}."
        )

    rr_preferences = parameters.get("rabota_ru") or {}
    auto_apply = bool(rr_preferences.get("auto_apply", False))

    output_folder: Path = parameters["outputFileDirectory"]
    applied_log = AppliedLog(output_folder / "applied_log.json")

    if is_still_blocked(output_folder, "rabota_ru"):
        logger.warning("rabota.ru is cooling down after a block — skipping.")
        return

    profile_dir = output_folder / ".chrome_profile_rabota_ru"
    client = RabotaRuClient()
    source: JobSource = RabotaRuSource(client)
    try:
        jobs = source.search(parameters)
    except PlatformBlockedError as e:
        logger.error(f"rabota.ru appears to have blocked us: {e}")
        mark_blocked(output_folder, "rabota_ru")
        notify(
            parameters,
            f"rabota.ru: похоже на блокировку ({e}). "
            "Площадка поставлена на паузу на 24ч.",
        )
        return
    logger.info(f"Found {len(jobs)} matching rabota.ru vacancies.")

    if auto_apply:
        RabotaRuSession(profile_dir).ensure_logged_in()

    sent_count = 0
    job_max_applications = _job_max_applications(parameters, "rabota_ru")
    for job in jobs:
        if sent_count >= job_max_applications:
            logger.info(
                f"Reached JOB_MAX_APPLICATIONS "
                f"({job_max_applications}) for this run."
            )
            break
        if _total_daily_limit_reached(parameters, applied_log):
            break
        if applied_log.already_applied(job):
            continue

        fit = score_job_fit(resume_pdf_path, job, llm_api_key)
        tier = classify_fit(
            fit.score,
            _job_min_score(parameters),
            _job_suitability_score(parameters),
        )
        if tier == "skip":
            logger.info(
                f"Skipping {job.role} at {job.company}: fit score "
                f"{fit.score}/10 below minimum."
            )
            applied_log.record(
                job, "", "", "skipped_low_fit", fit.score, fit.gaps
            )
            continue
        if tier == "weak":
            logger.info(
                f"{job.role} at {job.company}: weak fit "
                f"({fit.score}/10, gaps: {', '.join(fit.gaps)})."
            )

        try:
            cover_letter = generate_cover_letter_for_job(
                resume_pdf_path, job, llm_api_key
            )
        except Exception as e:
            logger.exception(
                f"Failed to generate cover letter for {job.role} at "
                f"{job.company}, skipping this vacancy: {e}"
            )
            continue

        if auto_apply:
            applied = client.apply(job.link, profile_dir)
            if applied:
                status: Literal["applied", "dry_run"] = "applied"
                logger.info(
                    f"Applied to {job.role} at {job.company} ({job.link})"
                )
            else:
                status = "dry_run"
                logger.warning(
                    "Кнопка 'Откликнуться' не найдена на "
                    f"{job.link} — записано как dry-run."
                )
        else:
            status = "dry_run"
            logger.info(
                f"[manual apply needed] {job.role} at {job.company} "
                f"({job.link})"
            )

        applied_log.record(
            job,
            cover_letter,
            resume_id="",
            status=status,
            score=fit.score,
            gaps=fit.gaps,
        )
        sent_count += 1


# {role}/{link} подставляются per-вакансия. Короткое и человеческое —
# см. комментарий в search_telegram про то, почему не всё письмо целиком.
TELEGRAM_INTRO_TEMPLATE_DEFAULT = (
    "Здравствуйте! Заинтересовала вакансия «{role}» ({link}). "
    "Расскажу подробнее о себе, если ещё актуально."
)


def search_telegram(parameters: dict, llm_api_key: str):
    """
    Ищет в настроенных Telegram-каналах свежие посты по
    ключевым словам из positions в work_preferences.yaml и пишет
    под каждый сопроводительное письмо на основе
    data_folder/resume.pdf.

    Если в посте нашёлся ровно один @username-контакт (extract_contact)
    и telegram.auto_message включён — то же сопроводительное письмо
    отправляется ему первым сообщением (с человекоподобной паузой,
    дневным лимитом и окном активных часов, см. apply_pacing), а диалог
    заводится в telegram_conversations.json для UI ("Диалоги").
    Иначе (нет контакта, или auto_message выключен) — как раньше,
    просто dry-run запись, годная только для ручного ответа.
    """
    data_folder: Path = parameters["dataFolder"]
    resume_pdf_path = data_folder / RESUME_PDF
    if not resume_pdf_path.exists():
        raise FileNotFoundError(
            f"Resume PDF not found: {resume_pdf_path}. Place your "
            f"resume as '{RESUME_PDF}' in {data_folder}."
        )

    secrets = ConfigValidator.load_yaml(parameters["secretsFile"])
    tg_secrets = secrets.get("telegram") or {}
    api_id = tg_secrets.get("api_id")
    api_hash = tg_secrets.get("api_hash")
    if not api_id or not api_hash:
        raise ConfigError("Missing telegram.api_id/api_hash in secrets.yaml")

    tg_preferences = parameters.get("telegram") or {}
    channels = tg_preferences.get("channels") or []
    if not channels:
        raise ConfigError(
            "telegram.channels is required in "
            "work_preferences.yaml (list of channel usernames)"
        )
    # Первое сообщение — короткое приветствие с интересом к вакансии,
    # а не всё сопроводительное письмо целиком: сразу вываливать длинный
    # текст (и тем более резюме) в первом же сообщении незнакомцу похоже
    # на рассылку ботом. cover_letter при этом всё равно генерируется и
    # попадает в applied_log/отчёт как обычно — пригодится, когда
    # разговор продолжится в чате и попросят прислать резюме/подробнее
    # рассказать о себе.
    auto_message = tg_preferences.get("auto_message", False)
    intro_template = tg_preferences.get(
        "intro_message_template", TELEGRAM_INTRO_TEMPLATE_DEFAULT
    )
    active_hours_start = tg_preferences.get("active_hours_start")
    active_hours_end = tg_preferences.get("active_hours_end")

    output_folder: Path = parameters["outputFileDirectory"]
    applied_log = AppliedLog(output_folder / "applied_log.json")
    conversations = TelegramConversations(
        output_folder / "telegram_conversations.json"
    )
    daily_message_limit = randomized_daily_limit(
        tg_preferences.get("daily_message_limit", 15)
    )

    with TelegramSourceClient(
        int(api_id), api_hash, output_folder / ".telegram_session"
    ) as client:
        source: JobSource = TelegramSource(client)
        jobs = source.search(parameters)

        logger.info(f"Found {len(jobs)} matching Telegram posts.")

        sent_count = 0
        job_max_applications = _job_max_applications(parameters, "telegram")
        for job in jobs:
            if sent_count >= job_max_applications:
                logger.info(
                    f"Reached JOB_MAX_APPLICATIONS "
                    f"({job_max_applications}) for this run."
                )
                break
            if _total_daily_limit_reached(parameters, applied_log):
                break
            if applied_log.already_applied(job):
                continue

            fit = score_job_fit(resume_pdf_path, job, llm_api_key)
            tier = classify_fit(
                fit.score,
                _job_min_score(parameters),
                _job_suitability_score(parameters),
            )
            if tier == "skip":
                logger.info(
                    f"Skipping {job.role} at {job.company}: fit score "
                    f"{fit.score}/10 below minimum."
                )
                applied_log.record(
                    job, "", "", "skipped_low_fit", fit.score, fit.gaps
                )
                continue
            if tier == "weak":
                logger.info(
                    f"{job.role} at {job.company}: weak fit "
                    f"({fit.score}/10, gaps: {', '.join(fit.gaps)})."
                )

            try:
                cover_letter = generate_cover_letter_for_job(
                    resume_pdf_path, job, llm_api_key
                )
            except Exception as e:
                logger.exception(
                    f"Failed to generate cover letter for {job.role} at "
                    f"{job.company}, skipping this vacancy: {e}"
                )
                continue

            # https://t.me/{channel}/{message_id} — см. mapping.py.
            channel = job.link.rsplit("/", 2)[-2]
            contact = extract_contact(job.description, channel)
            status: Literal["dry_run", "applied"] = "dry_run"
            if (
                contact
                and auto_message
                and not conversations.already_contacted(contact)
                and conversations.sent_today_count() < daily_message_limit
                and (
                    active_hours_start is None
                    or active_hours_end is None
                    or within_active_hours(
                        active_hours_start, active_hours_end
                    )
                )
            ):
                wait_before_telegram_message()
                intro_message = intro_template.format(
                    role=job.role, link=job.link
                )
                try:
                    client.send_message(contact, intro_message)
                except Exception as e:
                    logger.exception(
                        f"Failed to message @{contact} about {job.role}: {e}"
                    )
                else:
                    conversations.record_outbound(
                        contact, intro_message, job_link=job.link
                    )
                    status = "applied"
                    logger.info(
                        f"Messaged @{contact} about {job.role} ({job.link})"
                    )
            else:
                logger.info(f"[manual reply needed] {job.role} ({job.link})")

            applied_log.record(
                job,
                cover_letter,
                resume_id="",
                status=status,
                score=fit.score,
                gaps=fit.gaps,
            )
            sent_count += 1


def search_getmatch(parameters: dict, llm_api_key: str):
    """
    Ищет на GetMatch вакансии по work_preferences.yaml. Если
    getmatch.auto_apply — true, откликается кликом на "Откликнуться"
    на странице вакансии (проверено вручную на живом аккаунте с
    заполненным профилем: это один клик, без формы под
    сопроводительное письмо — GetMatch его нигде на сайте не
    запрашивает, письмо от LLM всё равно пишется и попадает в
    историю, просто не отправляется на площадку). Иначе — как раньше,
    каждое совпадение просто пишется как dry-run.
    """
    data_folder: Path = parameters["dataFolder"]
    resume_pdf_path = data_folder / RESUME_PDF
    if not resume_pdf_path.exists():
        raise FileNotFoundError(
            f"Resume PDF not found: {resume_pdf_path}. Place your "
            f"resume as '{RESUME_PDF}' in {data_folder}."
        )

    gm_preferences = parameters.get("getmatch") or {}
    auto_apply = bool(gm_preferences.get("auto_apply", False))
    email = None
    if auto_apply:
        secrets = ConfigValidator.load_yaml(parameters["secretsFile"])
        email = (secrets.get("getmatch") or {}).get("email")
        if not email:
            raise ConfigError(
                "getmatch.email is required in secrets.yaml when "
                "auto_apply is true"
            )

    output_folder: Path = parameters["outputFileDirectory"]
    applied_log = AppliedLog(output_folder / "applied_log.json")

    if is_still_blocked(output_folder, "getmatch"):
        logger.warning("GetMatch is cooling down after a block — skipping.")
        return

    profile_dir = output_folder / ".chrome_profile_getmatch"
    if auto_apply:
        assert email is not None  # enforced above when auto_apply is set
        GetMatchSession(profile_dir).ensure_logged_in(email)

    with GetMatchClient(profile_dir) as client:
        source: JobSource = GetMatchSource(client)
        try:
            jobs = source.search(parameters)
        except PlatformBlockedError as e:
            logger.error(f"GetMatch appears to have blocked us: {e}")
            mark_blocked(output_folder, "getmatch")
            notify(
                parameters,
                f"GetMatch: похоже на блокировку ({e}). "
                "Площадка поставлена на паузу на 24ч.",
            )
            return
        logger.info(f"Found {len(jobs)} matching GetMatch vacancies.")

        sent_count = 0
        job_max_applications = _job_max_applications(parameters, "getmatch")
        for job in jobs:
            if sent_count >= job_max_applications:
                logger.info(
                    f"Reached JOB_MAX_APPLICATIONS "
                    f"({job_max_applications}) for this run."
                )
                break
            if _total_daily_limit_reached(parameters, applied_log):
                break
            if applied_log.already_applied(job):
                continue

            fit = score_job_fit(resume_pdf_path, job, llm_api_key)
            tier = classify_fit(
                fit.score,
                _job_min_score(parameters),
                _job_suitability_score(parameters),
            )
            if tier == "skip":
                logger.info(
                    f"Skipping {job.role} at {job.company}: fit score "
                    f"{fit.score}/10 below minimum."
                )
                applied_log.record(
                    job, "", "", "skipped_low_fit", fit.score, fit.gaps
                )
                continue
            if tier == "weak":
                logger.info(
                    f"{job.role} at {job.company}: weak fit "
                    f"({fit.score}/10, gaps: {', '.join(fit.gaps)})."
                )

            try:
                cover_letter = generate_cover_letter_for_job(
                    resume_pdf_path, job, llm_api_key
                )
            except Exception as e:
                logger.exception(
                    f"Failed to generate cover letter for {job.role} at "
                    f"{job.company}, skipping this vacancy: {e}"
                )
                continue

            if auto_apply:
                applied = client.apply(job.link, cover_letter)
                if applied:
                    status: Literal["applied", "dry_run"] = "applied"
                    logger.info(
                        f"Applied to {job.role} at {job.company} ({job.link})"
                    )
                else:
                    status = "dry_run"
                    logger.warning(
                        "Кнопка 'Откликнуться' не найдена на "
                        f"{job.link} — записано как dry-run."
                    )
            else:
                status = "dry_run"
                logger.info(
                    f"[manual apply needed] {job.role} at {job.company} "
                    f"({job.link})"
                )

            applied_log.record(
                job,
                cover_letter,
                resume_id="",
                status=status,
                score=fit.score,
                gaps=fit.gaps,
            )
            sent_count += 1


def search_and_apply_linkedin(parameters: dict, llm_api_key: str):
    """
    Ищет вакансии LinkedIn Easy Apply и, если linkedin.auto_apply
    выставлен в true, откликается через многошаговую модалку —
    отвечая на отборочные вопросы через LLM на основе
    job_application_profile.yaml + resume.pdf, прикладывая
    резюме как есть (см. RESUME_PDF_LINKEDIN — отдельный файл под
    международные вакансии). Вход в аккаунт — вручную в открывшемся
    браузере (LinkedInSession), как и у остальных площадок проекта.
    Селекторы модалки Easy Apply (см. докстринг
    src/job_sources/linkedin/easy_apply.py) сверены на живой
    залогиненной сессии 2026-08-23 — нераспознанное поле анкеты
    по-прежнему просто пропускает эту вакансию, а не гадает, но это
    уже подстраховка от будущих изменений разметки LinkedIn, а не
    заведомо неподтверждённый код. Отдельного поля под PDF
    сопроводительного письма в форме Easy Apply нет вообще
    (подтверждено на реальной 5-шаговой форме) — cover_letter ниже
    только пишется в историю (applied_log), никуда не прикладывается.
    auto_apply: false по умолчанию независимо от того, что в итоге
    стоит в work_preferences.yaml — первый запуск всегда dry-run,
    чтобы проверить сгенерированные ответы до того, как что-то
    реально уйдёт — включайте true только после просмотра dry-run.
    """
    data_folder: Path = parameters["dataFolder"]
    resume_pdf_path = data_folder / RESUME_PDF_LINKEDIN
    if resume_pdf_path.exists():
        logger.info(f"Using {RESUME_PDF_LINKEDIN} for LinkedIn.")
    else:
        resume_pdf_path = data_folder / RESUME_PDF
        logger.info(
            f"{RESUME_PDF_LINKEDIN} not found — falling back to "
            f"{RESUME_PDF} for LinkedIn (likely the wrong language "
            "for an international audience; add "
            f"{RESUME_PDF_LINKEDIN} to use a separate resume here)."
        )
    if not resume_pdf_path.exists():
        raise FileNotFoundError(
            f"Resume PDF not found: {resume_pdf_path}. Place your "
            f"resume as '{RESUME_PDF}' (or '{RESUME_PDF_LINKEDIN}' "
            f"for a LinkedIn-specific one) in {data_folder}."
        )

    profile_path = data_folder / "job_application_profile.yaml"
    if not profile_path.exists():
        raise FileNotFoundError(
            f"job_application_profile.yaml not found: {profile_path}. "
            "Required for LinkedIn's screening questions "
            "(see data_folder_example/)."
        )
    profile = JobApplicationProfile(profile_path.read_text(encoding="utf-8"))

    li_preferences = parameters.get("linkedin") or {}
    auto_apply = bool(li_preferences.get("auto_apply", False))

    output_folder: Path = parameters["outputFileDirectory"]
    session = LinkedInSession(output_folder / ".linkedin_profile")
    applied_log = AppliedLog(output_folder / "applied_log.json")

    try:
        session.ensure_logged_in()
        source: JobSource = LinkedInSource(session.driver)
        jobs = source.search(parameters)
        logger.info(f"Found {len(jobs)} matching LinkedIn Easy Apply jobs.")

        resume_text = extract_pdf_text(str(resume_pdf_path))
        daily_limit = randomized_daily_limit(_linkedin_daily_limit(parameters))
        sent_count = 0
        job_max_applications = _job_max_applications(parameters, "linkedin")

        for job in jobs:
            if sent_count >= job_max_applications:
                logger.info(
                    f"Reached JOB_MAX_APPLICATIONS "
                    f"({job_max_applications}) for this run."
                )
                break
            if _total_daily_limit_reached(parameters, applied_log):
                break
            if applied_log.already_applied(job):
                continue
            if (
                auto_apply
                and parameters.get("apply_once_at_company")
                and applied_log.already_applied_to_company(job)
            ):
                logger.info(
                    f"Skipping {job.company} - already applied "
                    f"there (apply_once_at_company)."
                )
                continue
            if (
                auto_apply
                and applied_log.applied_today_count("linkedin") >= daily_limit
            ):
                logger.info(
                    f"Reached daily application limit ({daily_limit}) "
                    "for LinkedIn today."
                )
                notify(
                    parameters,
                    f"Дневной лимит откликов ({daily_limit}) достигнут "
                    "для LinkedIn.",
                )
                break

            fit = score_job_fit(resume_pdf_path, job, llm_api_key)
            tier = classify_fit(
                fit.score,
                _job_min_score(parameters),
                _job_suitability_score(parameters),
            )
            if tier == "skip":
                logger.info(
                    f"Skipping {job.role} at {job.company}: fit "
                    f"score {fit.score}/10 below minimum."
                )
                applied_log.record(
                    job, "", "", "skipped_low_fit", fit.score, fit.gaps
                )
                continue
            if tier == "weak":
                logger.info(
                    f"{job.role} at {job.company}: weak fit "
                    f"({fit.score}/10, gaps: {', '.join(fit.gaps)})."
                )

            if auto_apply:
                wait_before_apply()

            answerer = EasyApplyAnswerer(
                resume_text, profile, job, llm_api_key
            )
            submitted = run_easy_apply(
                session.driver,
                job,
                resume_pdf_path,
                answerer,
                dry_run=not auto_apply,
            )
            if not submitted:
                continue

            try:
                # force_russian=False: LinkedIn ждёт оформленный PDF
                # (см. docstring этой функции) и обычно
                # публикует вакансии на английском — язык здесь
                # по-прежнему определяется по тексту вакансии, а не
                # закреплён за русским, в отличие от остальных
                # площадок.
                cover_letter = generate_cover_letter_for_job(
                    resume_pdf_path,
                    job,
                    llm_api_key,
                    force_russian=False,
                )
            except Exception as e:
                logger.exception(
                    f"Failed to generate cover letter for {job.role} at "
                    f"{job.company}, skipping this vacancy: {e}"
                )
                continue
            status: Literal["applied", "dry_run"] = (
                "applied" if auto_apply else "dry_run"
            )
            applied_log.record(
                job,
                cover_letter,
                resume_id="",
                status=status,
                score=fit.score,
                gaps=fit.gaps,
            )
            sent_count += 1
    finally:
        session.quit()


def search_and_apply_habr_career(parameters: dict, llm_api_key: str):
    """
    Ищет вакансии на career.habr.com (positions из work_preferences.yaml
    ищутся через ?q= — свободный текстовый поиск) и, если
    habr_career.auto_apply выставлен в true, кликает
    "Откликнуться" — для вошедшего пользователя это мгновенная отправка
    одним кликом (подтверждено на живом аккаунте 2026-08-28, см.
    docstring HabrCareerClient.apply), без формы и без сопроводительного
    письма — cover_letter ниже только пишется в историю (applied_log),
    как и у LinkedIn.

    Официального API для личных ботов у Хабра нет (доступ — по ручному
    одобрению, не для этого сценария) — вход вручную в открывшемся
    браузере (HabrCareerSession, единый аккаунт Хабра, включая Google —
    бот никогда не создаёт аккаунт и не подставляет пароль сам). Один
    Chrome-процесс переиспользуется на все отклики за прогон (см.
    HabrCareerClient как контекстный менеджер), а не открывается заново
    на каждую вакансию.

    auto_apply: false по умолчанию независимо от того, что в итоге
    стоит в work_preferences.yaml — первый запуск всегда dry-run.
    """
    data_folder: Path = parameters["dataFolder"]
    resume_pdf_path = data_folder / RESUME_PDF
    if not resume_pdf_path.exists():
        raise FileNotFoundError(
            f"Resume PDF not found: {resume_pdf_path}. Place your "
            f"resume as '{RESUME_PDF}' in {data_folder}."
        )

    hc_preferences = parameters.get("habr_career") or {}
    auto_apply = bool(hc_preferences.get("auto_apply", False))

    output_folder: Path = parameters["outputFileDirectory"]
    applied_log = AppliedLog(output_folder / "applied_log.json")

    if is_still_blocked(output_folder, "habr_career"):
        logger.warning(
            "career.habr.com is cooling down after a block — skipping."
        )
        return

    profile_dir = output_folder / ".chrome_profile_habr_career"
    client = HabrCareerClient(profile_dir=profile_dir)
    source: JobSource = HabrCareerSource(client)
    try:
        jobs = source.search(parameters)
    except PlatformBlockedError as e:
        logger.error(f"career.habr.com appears to have blocked us: {e}")
        mark_blocked(output_folder, "habr_career")
        notify(
            parameters,
            f"career.habr.com: похоже на блокировку ({e}). "
            "Площадка поставлена на паузу на 24ч.",
        )
        return
    logger.info(f"Found {len(jobs)} matching career.habr.com vacancies.")

    if auto_apply:
        HabrCareerSession(profile_dir).ensure_logged_in()

    sent_count = 0
    job_max_applications = _job_max_applications(parameters, "habr_career")
    daily_limit = randomized_daily_limit(
        _daily_limit(parameters, "habr_career")
    )
    # Один Chrome-процесс на все клики "Откликнуться" за прогон вместо
    # открытия/закрытия браузера на каждую вакансию — client.apply()
    # ниже просто переходит на следующую страницу тем же окном.
    with client if auto_apply else nullcontext():
        for job in jobs:
            if sent_count >= job_max_applications:
                logger.info(
                    f"Reached JOB_MAX_APPLICATIONS "
                    f"({job_max_applications}) for this run."
                )
                break
            if _total_daily_limit_reached(parameters, applied_log):
                break
            if applied_log.already_applied(job):
                continue
            if (
                auto_apply
                and applied_log.applied_today_count("habr_career")
                >= daily_limit
            ):
                logger.info(
                    f"Reached daily application limit ({daily_limit}) "
                    "for career.habr.com today."
                )
                break

            fit = score_job_fit(resume_pdf_path, job, llm_api_key)
            tier = classify_fit(
                fit.score,
                _job_min_score(parameters),
                _job_suitability_score(parameters),
            )
            if tier == "skip":
                logger.info(
                    f"Skipping {job.role} at {job.company}: fit score "
                    f"{fit.score}/10 below minimum."
                )
                applied_log.record(
                    job, "", "", "skipped_low_fit", fit.score, fit.gaps
                )
                continue
            if tier == "weak":
                logger.info(
                    f"{job.role} at {job.company}: weak fit "
                    f"({fit.score}/10, gaps: {', '.join(fit.gaps)})."
                )

            try:
                cover_letter = generate_cover_letter_for_job(
                    resume_pdf_path, job, llm_api_key
                )
            except Exception as e:
                logger.exception(
                    f"Failed to generate cover letter for {job.role} at "
                    f"{job.company}, skipping this vacancy: {e}"
                )
                continue

            if auto_apply:
                applied = client.apply(job.link)
                if applied:
                    status: Literal["applied", "dry_run"] = "applied"
                    logger.info(
                        f"Applied to {job.role} at {job.company} "
                        f"({job.link})"
                    )
                else:
                    status = "dry_run"
                    logger.warning(
                        "Не удалось подтверждённо отправить отклик на "
                        f"{job.link} — записано как dry-run."
                    )
            else:
                status = "dry_run"
                logger.info(
                    f"[manual apply needed] {job.role} at {job.company} "
                    f"({job.link})"
                )

            applied_log.record(
                job,
                cover_letter,
                resume_id="",
                status=status,
                score=fit.score,
                gaps=fit.gaps,
            )
            sent_count += 1


ALL_SOURCES = [
    ("headhunter", search_and_apply_headhunter),
    ("superjob", search_and_apply_superjob),
    ("geekjob", search_geekjob),
    ("rabota_ru", search_rabota_ru),
    ("telegram", search_telegram),
    ("getmatch", search_getmatch),
    ("linkedin", search_and_apply_linkedin),
    ("habr_career", search_and_apply_habr_career),
]


def run_selected_sources(
    names: list[str], parameters: dict, llm_api_key: str
) -> None:
    """Прогоняет выбранные источники подряд, изолированно друг от
    друга (падение одного не останавливает остальные), с небольшой
    паузой между источниками — чтобы переключение между
    площадками подряд не выглядело скриптованным."""
    source_map = dict(ALL_SOURCES)
    selected = [
        (name, source_map[name]) for name in names if name in source_map
    ]
    output_folder = parameters.get("outputFileDirectory")
    before = (
        AppliedLog(output_folder / "applied_log.json").count_in_period("day")
        if output_folder
        else 0
    )

    for index, (name, search_fn) in enumerate(selected):
        logger.info(f"=== {name} ===")
        run_at = datetime.now()
        interval_hours = (parameters.get(name) or {}).get(
            "interval_hours", DEFAULT_INTERVAL_HOURS
        )
        next_run = run_at + timedelta(hours=interval_hours)
        try:
            search_fn(parameters, llm_api_key)
        except Exception as e:
            logger.exception(f"{name} failed, continuing with the rest: {e}")
            notify(parameters, f"CrossJob-AI: {name} упал — {e}")
            if output_folder:
                record_run_result(
                    output_folder,
                    name,
                    "error",
                    next_run,
                    run_at,
                    error=str(e),
                )
        else:
            # ponytail: без этого "Последний запуск"/статус на дашборде
            # обновлял только фоновый демон (Scheduler.run_once) — ручной
            # запуск ("Запустить выбранные") молча уходил мимо
            # .scheduler_state.json, и карточка площадки годами показывала
            # устаревший результат последнего planового тика, даже когда
            # ручные прогоны реально шли один за другим.
            if output_folder:
                record_run_result(output_folder, name, "ok", next_run, run_at)

        if index < len(selected) - 1:
            wait_between_sources()

    if output_folder:
        after = AppliedLog(output_folder / "applied_log.json").count_in_period(
            "day"
        )
        notify(
            parameters,
            f"Прогон завершён: отправлено {after - before} откликов "
            f"({', '.join(name for name, _ in selected)}).",
        )

    threshold = (parameters.get("limits") or {}).get(
        "llm_daily_cost_alert_usd"
    )
    if threshold and output_folder:
        if check_and_mark_alert(output_folder, float(threshold)):
            notify(
                parameters,
                f"CrossJob-AI: расходы на LLM сегодня превысили "
                f"${threshold}.",
            )

    if output_folder and check_and_mark_llm_exhausted_alert(output_folder):
        notify(
            parameters,
            "CrossJob-AI: похоже, все настроенные LLM-провайдеры сегодня "
            "недоступны (несколько ошибок подряд, ни одного успешного "
            "вызова) — вероятно, исчерпаны бесплатные лимиты. Вакансии "
            "пока оцениваются с fallback (без реальной LLM-проверки).",
        )


def run_all_sources(parameters: dict, llm_api_key: str) -> None:
    run_selected_sources(
        [name for name, _ in ALL_SOURCES], parameters, llm_api_key
    )


def notify(parameters: dict, text: str) -> None:
    """Best-effort уведомление в Telegram — отсутствие настроенного
    бота или сетевая ошибка не должны ронять прогон, только
    залогироваться. Реализация в telegram_notify.notify_from_secrets
    (общая с src.scheduler.Scheduler, чтобы не тянуть main.py туда
    циклическим импортом)."""
    notify_from_secrets(parameters, text)


def _prepare_external_form(
    parameters: dict,
    entry: dict,
    external_id: str,
    form_url: str,
    resume_pdf_path: Path,
    llm_api_key: str,
) -> None:
    """Открывает ссылку на внешнюю форму (Google Forms, подтверждено
    на живой форме — см. form_fill.py), читает вопросы, готовит
    черновик ответов через LLM и присылает в Telegram на
    подтверждение. Ничего не вводит и не отправляет сама — заполнение
    и submit ждут ответа "да <id>" (см. check_headhunter_replies →
    poll_approved_form_ids). Отдельный driver, а не тот, что держит
    чат hh.ru открытым — иначе переход на сторонний домен посреди
    цикла ответов на сообщения сломал бы остальные send_reply()."""
    output_folder: Path = parameters["outputFileDirectory"]
    profile_dir = output_folder / ".chrome_profile_headhunter_forms"
    driver = init_browser(profile_dir)
    try:
        driver.get(form_url)
        time.sleep(3)
        questions = scrape_form_questions(driver)
        if not questions:
            logger.warning(
                f"No recognizable questions on {form_url} (not a Google "
                "Form, or a different layout) — falling back to a plain "
                "link notification."
            )
            notify(
                parameters,
                "Работодатель просит заполнить анкету — не смог "
                f"прочитать вопросы автоматически: {entry['company']} — "
                f"{entry['title']}\n{form_url}",
            )
            return
        resume_text = extract_pdf_text(str(resume_pdf_path))
        job = Job(
            role=entry["title"], company=entry["company"], description=""
        )
        answers = draft_form_answers(questions, job, resume_text, llm_api_key)
    except Exception as e:
        logger.exception(f"Failed to prepare external form {form_url}: {e}")
        notify(
            parameters,
            "Работодатель просит заполнить анкету — не смог обработать "
            f"её автоматически: {entry['company']} — {entry['title']}\n"
            f"{form_url}",
        )
        return
    finally:
        driver.quit()

    form_id = save_pending_form(
        output_folder,
        entry["company"],
        entry["title"],
        form_url,
        external_id,
        questions_to_dicts(questions),
        answers_to_dicts(answers),
    )
    notify_pending_form(
        parameters,
        form_id,
        entry["company"],
        entry["title"],
        form_url,
        format_questions_and_answers(questions, answers),
    )


def _process_pending_form_approvals(
    parameters: dict, llm_api_key: str
) -> None:
    """Раз за прогон проверяет Telegram на команды по анкетам (см.
    telegram_approval.poll_form_commands: подтвердить/перегенерировать
    /поправить пункт). Реальное заполнение и submit на стороннем
    сайте происходит только для action=="approve" — единственное
    место всего HH-конвейера, которое жмёт submit не на hh.ru, и
    делает это только после явного ответа пользователя в Telegram."""
    secrets = ConfigValidator.load_yaml(parameters["secretsFile"])
    notifications = secrets.get("notifications") or {}
    bot_token = notifications.get("telegram_bot_token")
    chat_id = notifications.get("telegram_chat_id")
    if not bot_token or not chat_id:
        return

    output_folder: Path = parameters["outputFileDirectory"]
    try:
        commands = poll_form_commands(bot_token, chat_id, output_folder)
    except Exception as e:
        logger.warning(f"Failed to poll Telegram for form commands: {e}")
        return

    for cmd in commands:
        form_id = cmd["form_id"]
        record = get_pending_form(output_folder, form_id)
        if record is None:
            continue

        if cmd["action"] == "approve":
            _submit_approved_form(parameters, output_folder, form_id, record)
        elif cmd["action"] == "regenerate":
            _regenerate_form_draft(
                parameters, output_folder, form_id, record, llm_api_key
            )
        elif cmd["action"] == "edit":
            _edit_form_answer(
                parameters,
                output_folder,
                form_id,
                record,
                cmd["question_index"],
                cmd["new_text"],
            )


def _submit_approved_form(
    parameters: dict, output_folder: Path, form_id: str, record: dict
) -> None:
    profile_dir = output_folder / ".chrome_profile_headhunter_forms"
    driver = init_browser(profile_dir)
    try:
        driver.get(record["form_url"])
        time.sleep(3)
        fill_form(
            driver,
            dicts_to_questions(record["questions"]),
            dicts_to_answers(record["answers"]),
        )
        submit_buttons = driver.find_elements(
            By.XPATH, '//span[text()="Submit" or text()="Отправить"]'
        )
        if submit_buttons:
            submit_buttons[0].click()
            time.sleep(2)
            logger.info(
                f"Submitted external form for {record['company']} — "
                f"{record['title']} after Telegram approval."
            )
            notify(
                parameters,
                f"Анкета отправлена: {record['company']} — "
                f"{record['title']}",
            )
        else:
            logger.warning(
                f"Filled form for {record['company']} but no Submit "
                "button found — form left open, not submitted."
            )
    except Exception as e:
        logger.exception(f"Failed to fill/submit approved form {form_id}: {e}")
    finally:
        driver.quit()
        remove_pending_form(output_folder, form_id)


def _regenerate_form_draft(
    parameters: dict,
    output_folder: Path,
    form_id: str,
    record: dict,
    llm_api_key: str,
) -> None:
    questions = dicts_to_questions(record["questions"])
    job = Job(role=record["title"], company=record["company"], description="")
    resume_pdf_path = parameters["dataFolder"] / RESUME_PDF
    try:
        resume_text = extract_pdf_text(str(resume_pdf_path))
        answers = draft_form_answers(questions, job, resume_text, llm_api_key)
    except Exception as e:
        logger.exception(f"Failed to regenerate form draft {form_id}: {e}")
        return
    updated = update_pending_form_answers(
        output_folder, form_id, answers_to_dicts(answers)
    )
    if updated is None:
        return
    notify_pending_form(
        parameters,
        form_id,
        updated["company"],
        updated["title"],
        updated["form_url"],
        format_questions_and_answers(questions, answers),
        is_update=True,
    )


def _edit_form_answer(
    parameters: dict,
    output_folder: Path,
    form_id: str,
    record: dict,
    question_index: int,
    new_text: str,
) -> None:
    question = next(
        (q for q in record["questions"] if q["index"] == question_index), None
    )
    if question is None:
        logger.warning(
            f"Form {form_id}: no question with index {question_index}."
        )
        return

    if question["kind"] == "text":
        new_answer = {
            "index": question_index,
            "text_answer": new_text,
            "selected_options": None,
        }
    else:
        matched = next(
            (
                o
                for o in question["options"]
                if new_text.lower() in o.lower()
                or o.lower() in new_text.lower()
            ),
            None,
        )
        new_answer = {
            "index": question_index,
            "text_answer": None,
            "selected_options": [matched or new_text],
        }

    answers = [a for a in record["answers"] if a["index"] != question_index]
    answers.append(new_answer)
    updated = update_pending_form_answers(output_folder, form_id, answers)
    if updated is None:
        return
    notify_pending_form(
        parameters,
        form_id,
        updated["company"],
        updated["title"],
        updated["form_url"],
        format_questions_and_answers(
            dicts_to_questions(updated["questions"]),
            dicts_to_answers(updated["answers"]),
        ),
        is_update=True,
    )


def _answer_headhunter_messages(
    parameters: dict,
    driver,
    applied_log: AppliedLog,
    llm_api_key: str,
) -> None:
    """Автоответ на сообщения работодателя в чате hh.ru — через ту же
    браузерную сессию, что и поиск/отклик (см. HeadHunterSession и
    browser_replies.py, НЕ проверено на живом аккаунте, как и
    остальные best-effort браузерные места этого источника).
    Выключено по умолчанию: включается через headhunter.auto_reply в
    work_preferences.yaml, как и остальные auto_*-флаги в проекте.
    Если работодатель прислал ссылку на внешнюю форму — сюда мы не
    заходим и ничего не заполняем, только уведомляем пользователя
    (см. find_external_link): вводить его личные данные на незнакомом
    сайте без явного подтверждения нельзя."""
    hh_preferences = parameters.get("headhunter") or {}
    if not hh_preferences.get("auto_reply"):
        return

    data_folder: Path = parameters["dataFolder"]
    resume_pdf_path = data_folder / RESUME_PDF
    if not resume_pdf_path.exists():
        return

    secrets = ConfigValidator.load_yaml(parameters["secretsFile"])
    github_config = secrets.get("github") or {}
    github_summary = ""
    if github_config.get("username"):
        github_summary = fetch_github_summary(
            github_config["username"], github_config.get("token")
        )
        if github_summary:
            github_summary = f"GitHub-профиль кандидата:\n{github_summary}"

    preferences_summary = build_preferences_summary(parameters)

    try:
        messages = fetch_new_employer_messages(driver)
    except Exception as e:
        logger.warning(f"Failed to fetch hh.ru chat messages: {e}")
        return

    for message in messages:
        external_id = message["external_id"]
        message_id = message["message_id"]

        entry = applied_log.find_by_source_and_external_id(
            "headhunter", external_id
        )
        if entry is None or entry["status"] != "applied":
            continue
        if message_id == entry.get("last_replied_message_id"):
            continue

        external_link = find_external_link(message["text"])
        if external_link:
            logger.info(
                f"{entry['company']} — {entry['title']}: работодатель "
                f"прислал ссылку на внешнюю форму ({external_link}) — "
                "готовлю черновик и жду подтверждения в Telegram."
            )
            _prepare_external_form(
                parameters,
                entry,
                external_id,
                external_link,
                resume_pdf_path,
                llm_api_key,
            )
            applied_log.mark_replied("headhunter", external_id, message_id)
            continue

        try:
            if not message_needs_reply(message["text"], llm_api_key):
                logger.info(
                    f"{entry['company']} — {entry['title']}: сообщение не "
                    "требует ответа (статус/автоматика) — молча "
                    "помечаем прочитанным, не отвечаем."
                )
                applied_log.mark_replied("headhunter", external_id, message_id)
                continue
        except Exception as e:
            logger.warning(
                f"Failed to classify message for {entry['company']}, "
                f"replying anyway to be safe: {e}"
            )

        try:
            reply_text = generate_reply(
                resume_pdf_path,
                message["text"],
                entry["title"],
                entry["company"],
                preferences_summary,
                llm_api_key,
                github_summary=github_summary,
            )
            if not send_reply(driver, reply_text):
                logger.warning(
                    "Не нашли поле ввода чата на hh.ru для ответа "
                    f"{entry['company']} — разметка могла измениться."
                )
                continue
        except Exception as e:
            logger.exception(
                f"Failed to auto-reply to {entry['company']}: {e}"
            )
            continue

        applied_log.mark_replied("headhunter", external_id, message_id)
        logger.info(f"Auto-replied to {entry['company']} — {entry['title']}")
        notify(
            parameters,
            f"Автоответ отправлен: {entry['company']} — {entry['title']}",
        )


def check_headhunter_replies(parameters: dict, llm_api_key: str):
    """
    Если headhunter.auto_reply: true — автоматически отвечает на новые
    сообщения работодателя в чате hh.ru через браузерную сессию (см.
    _answer_headhunter_messages/HeadHunterSession). В отличие от
    остальных check_*_replies в проекте, здесь нет отдельной сверки
    статусов переговоров (viewed/invited/...) — это требует парсинга
    ещё и списка /applicant/negotiations поверх чатов, не запрошено
    явно и не проверено на живом аккаунте; добавить при необходимости.
    Ничего не делает, если headhunter.auto_reply выключен (по
    умолчанию) — не открывает браузер зря.
    """
    hh_preferences = parameters.get("headhunter") or {}
    if not hh_preferences.get("auto_reply"):
        return

    output_folder: Path = parameters["outputFileDirectory"]
    profile_dir = output_folder / ".chrome_profile_headhunter"
    applied_log = AppliedLog(output_folder / "applied_log.json")

    driver = init_browser(profile_dir)
    try:
        _answer_headhunter_messages(
            parameters, driver, applied_log, llm_api_key
        )
    finally:
        driver.quit()

    _process_pending_form_approvals(parameters, llm_api_key)


def _format_telegram_status(parameters: dict, applied_log: AppliedLog) -> str:
    output_folder: Path = parameters["outputFileDirectory"]
    state = load_state(output_folder)
    lines = [
        f"Всего откликов сегодня: {applied_log.applied_today_count_all()}"
    ]
    for name, _ in ALL_SOURCES:
        source_config = parameters.get(name) or {}
        if not source_config.get("schedule_enabled"):
            continue
        info = state.get(name) or {}
        status = info.get("status")
        dot = "🟢" if status == "ok" else "🔴" if status == "error" else "⚪"
        count = applied_log.applied_today_count(name)
        limit = _daily_limit(parameters, name)
        line = f"{dot} {name}: {count}/{limit}"
        if info.get("last_error"):
            line += f" — {info['last_error'].splitlines()[0][:80]}"
        lines.append(line)
    return "\n".join(lines)


def check_telegram_commands(parameters: dict, llm_api_key: str) -> None:
    """Раз в несколько минут проверяет Telegram на команды дистанционного
    управления (/status, /pause <площадка>, /resume <площадка>) — тот
    же bot_token/chat_id, что уведомления и подтверждение анкет HH, но
    свой offset-файл (poll_control_commands) и не завязано на
    headhunter.auto_reply, в отличие от _process_pending_form_approvals
    (та гоняется только вместе с проверкой чата HH)."""
    secrets = ConfigValidator.load_yaml(parameters["secretsFile"])
    notifications = secrets.get("notifications") or {}
    bot_token = notifications.get("telegram_bot_token")
    chat_id = notifications.get("telegram_chat_id")
    if not bot_token or not chat_id:
        return

    output_folder: Path = parameters["outputFileDirectory"]
    try:
        commands = poll_control_commands(bot_token, chat_id, output_folder)
    except Exception as e:
        logger.warning(f"Failed to poll Telegram for control commands: {e}")
        return
    if not commands:
        return

    applied_log = AppliedLog(output_folder / "applied_log.json")
    for cmd in commands:
        action = cmd["action"]
        if action == "help":
            send_notification(bot_token, chat_id, _TELEGRAM_HELP_TEXT)
        elif action == "status":
            send_notification(
                bot_token,
                chat_id,
                _format_telegram_status(parameters, applied_log),
            )
        elif action in ("pause", "resume"):
            source = cmd["source"]
            if source not in dict(SCHEDULER_SOURCES):
                send_notification(
                    bot_token, chat_id, f"Неизвестная площадка: {source}"
                )
                continue
            set_source_field(
                parameters["dataFolder"] / WORK_PREFERENCES_YAML,
                source,
                "schedule_enabled",
                action == "resume",
            )
            verb = (
                "возобновлена" if action == "resume" else "поставлена на паузу"
            )
            send_notification(bot_token, chat_id, f"{source}: {verb}.")


def cleanup_headhunter_negotiations(parameters: dict) -> None:
    """Отменяет зависшие отклики на hh.ru (аналог
    hh-applicant-tool/operations/clear_negotiations.py) — деструктивно
    (реальные отклики на аккаунте), поэтому вызывается ТОЛЬКО вручную
    (пункт меню / --auto cleanup_hh_negotiations), никогда не входит в
    ALL_SOURCES/SCHEDULER_SOURCES и не запускается автоматически из
    основного цикла. Единственный gate — headhunter.auto_cleanup_negotiations
    (по умолчанию false, как и остальные auto_*-флаги этого источника):
    при false ничего не делает даже если запущено вручную; при true
    реально кликает "Отменить отклик" для каждого найденного
    отклика — под cleanup_older_than_days (по умолчанию 30) или в
    статусе "отказ", если возраст не задан отдельно (см.
    list_withdrawable_negotiations)."""
    hh_preferences = parameters.get("headhunter") or {}
    if not hh_preferences.get("auto_cleanup_negotiations"):
        logger.info(
            "headhunter.auto_cleanup_negotiations выключен — ничего не "
            "отменяем (это опциональное обслуживающее действие, не "
            "часть основного цикла)."
        )
        return

    older_than_days = hh_preferences.get("cleanup_older_than_days", 30)
    output_folder: Path = parameters["outputFileDirectory"]
    profile_dir = output_folder / ".chrome_profile_headhunter"

    driver = init_browser(profile_dir)
    withdrawn = 0
    try:
        entries = list_withdrawable_negotiations(driver, older_than_days)
        logger.info(f"Найдено {len(entries)} отклик(ов) для отмены.")
        for entry in entries:
            ok = withdraw_negotiation(driver, entry)
            logger.info(
                f"{'Отменён' if ok else 'Не удалось отменить'} отклик "
                f"{entry['vacancy_url']} (отказ={entry['is_discard']}, "
                f"дней без обновления={entry['days_old']})"
            )
            if ok:
                withdrawn += 1
    finally:
        driver.quit()

    notify(
        parameters,
        f"HeadHunter: отменено {withdrawn} зависших отклик(ов).",
    )


def block_headhunter_employer(parameters: dict, company: str) -> bool:
    """Блокирует работодателя на стороне hh.ru (серверный бан, жёстче
    локального company_blacklist) — вызывается ТОЛЬКО вручную из
    дашборда (POST /api/headhunter/block-employer), никогда
    автоматически. Резолвит company в ссылку через уже существующий
    AppliedLog.find_by_company; если ни одной подходящей записи нет —
    возвращает False, не открывая браузер зря."""
    output_folder: Path = parameters["outputFileDirectory"]
    applied_log = AppliedLog(output_folder / "applied_log.json")
    matches = [
        e
        for e in applied_log.find_by_company(company)
        if e["source"] == "headhunter"
    ]
    if not matches:
        logger.warning(
            f"Не нашли отклик на HeadHunter для компании '{company}' — "
            "нечего блокировать."
        )
        return False

    profile_dir = output_folder / ".chrome_profile_headhunter"
    driver = init_browser(profile_dir)
    try:
        ok = block_employer(driver, matches[0]["link"])
    finally:
        driver.quit()

    if ok:
        notify(
            parameters, f"HeadHunter: работодатель '{company}' заблокирован."
        )
    return ok


def clone_headhunter_resume(parameters: dict, resume_id: str) -> Optional[str]:
    """Клонирует резюме на hh.ru кликом (браузерный аналог
    hh-applicant-tool clone_resume.py — та операция там идёт через
    OAuth API, здесь заменена на клик, см. browser_resume.clone_resume).
    Вызывается ТОЛЬКО вручную из дашборда, не часть автоматического
    цикла."""
    output_folder: Path = parameters["outputFileDirectory"]
    profile_dir = output_folder / ".chrome_profile_headhunter"
    driver = init_browser(profile_dir)
    try:
        new_url = clone_resume(driver, resume_id)
    finally:
        driver.quit()

    if new_url:
        notify(parameters, f"HeadHunter: резюме склонировано — {new_url}")
    return new_url


def create_headhunter_resume_draft(parameters: dict) -> Optional[str]:
    """Запускает мастер создания резюме на hh.ru с предзаполненной
    желаемой должностью (первая из headhunter.positions/positions в
    work_preferences.yaml) — остальное пользователь дозаполняет
    вручную, см. browser_resume.start_resume_draft про обоснование.
    Вызывается ТОЛЬКО вручную из дашборда."""
    hh_preferences = parameters.get("headhunter") or {}
    positions = hh_preferences.get("positions") or parameters.get("positions")
    desired_title = (positions or [""])[0]
    if not desired_title:
        logger.warning(
            "Нет ни одной должности в positions — нечем предзаполнить "
            "черновик резюме, отменяю."
        )
        return None

    output_folder: Path = parameters["outputFileDirectory"]
    profile_dir = output_folder / ".chrome_profile_headhunter"
    driver = init_browser(profile_dir)
    try:
        draft_url = start_resume_draft(driver, desired_title)
    finally:
        driver.quit()

    if draft_url:
        notify(
            parameters,
            f"HeadHunter: черновик резюме создан — {draft_url}. "
            "Доделайте вручную на hh.ru.",
        )
    return draft_url


def check_superjob_replies(parameters: dict):
    """То же самое, что check_headhunter_replies, только для
    SuperJob. Использует /messages/ вместо /negotiations — про
    оговорку "названия полей не до конца проверены" см.
    SuperJobClient.list_messages и
    reply_check.print_superjob_replies."""
    secrets = ConfigValidator.load_yaml(parameters["secretsFile"])
    sj_secrets = secrets.get("superjob") or {}
    client_id = sj_secrets.get("client_id")
    client_secret = sj_secrets.get("client_secret")
    if not client_id or not client_secret:
        raise ConfigError(
            "Missing superjob.client_id/client_secret in secrets.yaml"
        )

    output_folder: Path = parameters["outputFileDirectory"]
    auth = SuperJobAuth(
        client_id, client_secret, output_folder / ".superjob_token.json"
    )
    client = SuperJobClient(auth.get_access_token(), client_secret)
    applied_log = AppliedLog(output_folder / "applied_log.json")

    print_superjob_replies(
        client.list_messages(),
        applied_log,
        on_new_reply=lambda entry, state: notify(
            parameters,
            f"Новый ответ: {entry['company']} — {entry['title']}: {state}",
        ),
    )


def _check_sj_replies_scheduled(parameters: dict, llm_api_key: str) -> None:
    """Обёртка под сигнатуру Scheduler (parameters, llm_api_key) —
    check_superjob_replies не использует LLM (только уведомление о
    новых ответах, без AI-автоответа, в отличие от HH), поэтому
    llm_api_key здесь не нужен, просто игнорируется."""
    check_superjob_replies(parameters)


def check_telegram_replies(parameters: dict, llm_api_key: str) -> None:
    """Проверяет личные диалоги, заведённые search_telegram
    (telegram.auto_message), на новые ответы контактов — то же самое,
    что check_superjob_replies: только
    уведомление в Telegram-бот, без AI-автоответа (в отличие от HH,
    где есть чат с явной кнопкой "ответить" на площадке — здесь это
    личный диалог самого пользователя, автоматически отвечать в него
    от его имени не тот случай)."""
    secrets = ConfigValidator.load_yaml(parameters["secretsFile"])
    tg_secrets = secrets.get("telegram") or {}
    api_id = tg_secrets.get("api_id")
    api_hash = tg_secrets.get("api_hash")
    if not api_id or not api_hash:
        return

    output_folder: Path = parameters["outputFileDirectory"]
    conversations = TelegramConversations(
        output_folder / "telegram_conversations.json"
    )
    active_conversations = conversations.all()
    if not active_conversations:
        return

    with TelegramSourceClient(
        int(api_id), api_hash, output_folder / ".telegram_session"
    ) as client:
        for conv in active_conversations:
            contact = conv["contact"]
            try:
                new_messages = client.new_incoming_messages(
                    contact, conv.get("last_incoming_id", 0)
                )
            except Exception as e:
                logger.warning(f"Failed to poll @{contact} on Telegram: {e}")
                continue
            for message in reversed(new_messages):
                text = (message.text or "").strip()
                if not text:
                    continue
                conversations.record_inbound(
                    contact, text, message.id, message.date
                )
                notify(
                    parameters,
                    f"Новый ответ в Telegram от @{contact}: {text}",
                )


# ponytail: check_*_replies не входят в ALL_SOURCES (это не
# "поиск+отклик", а отдельные проверки чата/переговоров) — но
# демону/веб-планировщику нужно их видеть, иначе headhunter.auto_reply
# (и сама возможность увидеть новые ответы SJ/Telegram) никогда не
# срабатывает сам по себе, только вручную через --auto check_*_replies.
# У каждого свой schedule_enabled/interval_hours блок в
# work_preferences.yaml (toplevel, не внутри headhunter:/superjob:/
# telegram:), т.к. Scheduler матчит по имени ключа словаря.
SCHEDULER_SOURCES = {
    **dict(ALL_SOURCES),
    "check_hh_replies": check_headhunter_replies,
    "check_sj_replies": _check_sj_replies_scheduled,
    "check_telegram_replies": check_telegram_replies,
    "check_telegram_commands": check_telegram_commands,
}


def show_application_history(parameters: dict):
    """
    Спрашивает необязательную строку поиска по компании/названию
    и печатает подходящие отправленные заявки (компания, название,
    ссылка, дата, сопроводительное письмо).
    """
    output_folder: Path = parameters["outputFileDirectory"]
    applied_log = AppliedLog(output_folder / "applied_log.json")

    report_path = output_folder / "applications.html"
    if report_path.exists():
        print(f"Full report (open in a browser): {report_path}\n")

    answer = inquirer.prompt(
        [
            inquirer.Text(
                "query",
                message="Search by company/title (leave blank for all)",
            )
        ]
    )
    query = (answer or {}).get("query") or ""

    entries = applied_log.find_by_company(query)
    if not entries:
        print("No matching applications found.")
        return

    for entry in entries:
        print(
            f"\n{entry['applied_at']} [{entry['status']}] "
            f"{entry['company']} — {entry['title']}"
        )
        print(f"  {entry['link']}")
        print(f"  Cover letter: {entry['cover_letter'][:200]}...")


def export_application_history(parameters: dict):
    """Экспортирует всю историю заявок в TXT или PDF для
    оффлайн-архива — TXT это просто текстовый дамп, а PDF
    переиспользует уже отрендеренный HTML-отчёт через
    HTML_to_PDF на Selenium, вместо добавления новой
    зависимости."""
    output_folder: Path = parameters["outputFileDirectory"]
    applied_log = AppliedLog(output_folder / "applied_log.json")
    entries = applied_log.find_by_company("")
    if not entries:
        print("No applications to export.")
        return

    answer = inquirer.prompt(
        [
            inquirer.List(
                "format", message="Export format", choices=["TXT", "PDF"]
            ),
        ]
    )
    export_format = (answer or {}).get("format")
    if not export_format:
        return

    if export_format == "TXT":
        lines = [
            f"{e['applied_at']} [{e['status']}] {e['source']} — "
            f"{e['company']} — {e['title']}\n"
            f"  Salary: {e.get('salary') or '-'}\n"
            f"  Company site: {e.get('company_url') or '-'}\n"
            f"  Link: {e['link']}\n"
            for e in entries
        ]
        out_path = output_folder / "applications_export.txt"
        out_path.write_text("\n".join(lines), encoding="utf-8")
    else:
        html_content = (output_folder / "applications.html").read_text(
            encoding="utf-8"
        )
        driver = init_browser()
        try:
            pdf_base64 = HTML_to_PDF(html_content, driver)
        finally:
            driver.quit()
        out_path = output_folder / "applications_export.pdf"
        out_path.write_bytes(base64.b64decode(pdf_base64))

    print(f"Exported: {out_path}")


def append_to_company_blacklist(
    config_file: Path, companies: list[str]
) -> None:
    """Дописывает компании в company_blacklist текстово (не через
    yaml.safe_dump всего файла), чтобы не потерять комментарии и
    форматирование, которые уже есть в work_preferences.yaml."""
    text = config_file.read_text(encoding="utf-8")
    lines = text.splitlines()
    new_entries = [f"  - {company}" for company in companies]
    for index, line in enumerate(lines):
        if line.strip() == "company_blacklist:":
            insert_at = index + 1
            lines[insert_at:insert_at] = new_entries
            config_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return
    text += "\n\ncompany_blacklist:\n" + "\n".join(new_entries) + "\n"
    config_file.write_text(text, encoding="utf-8")


def suggest_blacklist_additions(
    config_file: Path, output_folder: Path
) -> None:
    """Не добавляет автоматически — только предлагает через чекбокс
    компании без единого ответа за min_attempts+ реальных откликов
    (см. AppliedLog.suggest_blacklist_candidates)."""
    applied_log = AppliedLog(output_folder / "applied_log.json")
    candidates = applied_log.suggest_blacklist_candidates()
    if not candidates:
        return
    answer = inquirer.prompt(
        [
            inquirer.Checkbox(
                "companies",
                message=(
                    f"{len(candidates)} компаний без единого ответа за "
                    "3+ откликов — добавить в company_blacklist?"
                ),
                choices=candidates,
            )
        ]
    )
    chosen = (answer or {}).get("companies") or []
    if chosen:
        append_to_company_blacklist(config_file, chosen)
        logger.info(f"Added to company_blacklist: {', '.join(chosen)}")


def handle_inquiries(
    selected_actions: str, parameters: dict, llm_api_key: str
):
    """
    Обычная цепочка if, сравнивающих строку с пунктами меню
    prompt_user_action() — сознательно без Enum/dict-диспетчера,
    чтобы не плодить второй источник правды для тех же строк
    выбора.

    :param selected_actions: выбранное пользователем действие.
    :param parameters: словарь параметров конфигурации.
    :param llm_api_key: ключ API языковой модели.
    """
    try:
        if selected_actions:
            if "Generate Resume" == selected_actions:
                logger.info("Crafting a standout professional resume...")
                create_resume_pdf(parameters, llm_api_key)

            if (
                "Generate Resume Tailored for Job Description"
                == selected_actions
            ):
                logger.info(
                    "Customizing your resume to enhance your job "
                    "application..."
                )
                create_resume_pdf_job_tailored(parameters, llm_api_key)

            if (
                "Generate Tailored Cover Letter for Job Description"
                == selected_actions
            ):
                logger.info(
                    "Designing a personalized cover letter to "
                    "enhance your job application..."
                )
                create_cover_letter(parameters, llm_api_key)

            if "Search & Apply on HeadHunter" == selected_actions:
                logger.info(
                    "Searching HeadHunter and preparing applications..."
                )
                search_and_apply_headhunter(parameters, llm_api_key)

            if "Search & Apply on SuperJob" == selected_actions:
                logger.info("Searching SuperJob and preparing applications...")
                search_and_apply_superjob(parameters, llm_api_key)

            if "Search & Apply on geekjob.ru" == selected_actions:
                logger.info("Searching geekjob.ru...")
                search_geekjob(parameters, llm_api_key)

            if "Search & Apply on rabota.ru" == selected_actions:
                logger.info("Searching rabota.ru...")
                search_rabota_ru(parameters, llm_api_key)

            if "Search Telegram channels (manual reply)" == selected_actions:
                logger.info("Searching Telegram channels...")
                search_telegram(parameters, llm_api_key)

            if "Search & Apply on GetMatch" == selected_actions:
                logger.info("Searching GetMatch...")
                search_getmatch(parameters, llm_api_key)

            if "Search & Apply on LinkedIn" == selected_actions:
                logger.info("Searching LinkedIn Easy Apply jobs...")
                search_and_apply_linkedin(parameters, llm_api_key)

            if "Search & Apply on Habr Career" == selected_actions:
                logger.info("Searching career.habr.com...")
                search_and_apply_habr_career(parameters, llm_api_key)

            if "Search selected sources" == selected_actions:
                names = prompt_selected_sources()
                if names:
                    run_selected_sources(names, parameters, llm_api_key)
                else:
                    logger.warning("No sources selected.")

            if "Check HeadHunter replies" == selected_actions:
                check_headhunter_replies(parameters, llm_api_key)

            if "Clean up stale HeadHunter negotiations" == selected_actions:
                cleanup_headhunter_negotiations(parameters)

            if "Check SuperJob replies" == selected_actions:
                check_superjob_replies(parameters)

            if "Show sent applications" == selected_actions:
                show_application_history(parameters)

            if "Export application history (TXT/PDF)" == selected_actions:
                export_application_history(parameters)

        else:
            logger.warning("No actions selected. Nothing to execute.")
    except Exception as e:
        logger.exception(f"An error occurred while handling inquiries: {e}")
        raise


def prompt_user_action() -> str:
    """
    Спрашивает через inquirer, какое действие выполнить.

    :return: выбранное действие.
    """
    try:
        questions = [
            inquirer.List(
                "action",
                message="Select the action you want to perform:",
                choices=[
                    "Generate Resume",
                    "Generate Resume Tailored for Job Description",
                    "Generate Tailored Cover Letter for Job Description",
                    "Search & Apply on HeadHunter",
                    "Search & Apply on SuperJob",
                    "Search & Apply on geekjob.ru",
                    "Search & Apply on rabota.ru",
                    "Search Telegram channels (manual reply)",
                    "Search & Apply on GetMatch",
                    "Search & Apply on LinkedIn",
                    "Search & Apply on Habr Career",
                    "Search selected sources",
                    "Check HeadHunter replies",
                    "Clean up stale HeadHunter negotiations",
                    "Check SuperJob replies",
                    "Show sent applications",
                    "Export application history (TXT/PDF)",
                ],
            ),
        ]
        answer = inquirer.prompt(questions)
        if answer is None:
            print("No answer provided. The user may have interrupted.")
            return ""
        return answer.get("action", "")
    except Exception as e:
        print(f"An error occurred: {e}")
        return ""


def prompt_selected_sources() -> list[str]:
    """Checkbox вместо жёстко зафиксированного "все источники сразу" —
    пользователь сам решает, что запускать за один прогон."""
    questions = [
        inquirer.Checkbox(
            "sources",
            message=(
                "Select sources to search "
                "(space to toggle, enter to confirm)"
            ),
            choices=[
                ("HeadHunter", "headhunter"),
                ("SuperJob", "superjob"),
                ("geekjob.ru (manual apply)", "geekjob"),
                ("rabota.ru (manual apply)", "rabota_ru"),
                ("Telegram channels (manual reply)", "telegram"),
                ("GetMatch (manual apply)", "getmatch"),
                (
                    "LinkedIn (experimental, not verified live)",
                    "linkedin",
                ),
                (
                    "Habr Career (experimental, not verified live)",
                    "habr_career",
                ),
            ],
        ),
    ]
    answer = inquirer.prompt(questions)
    return (answer or {}).get("sources") or []


@click.command()
@click.option(
    "--auto",
    type=str,
    default=None,
    help=(
        "Run non-interactively (for cron) instead of showing the menu: "
        "one of headhunter/superjob/geekjob/rabota_ru/telegram/"
        "getmatch/linkedin/habr_career/all/"
        "check_hh_replies/"
        "check_sj_replies/"
        "check_telegram_replies/"
        "cleanup_hh_negotiations, or "
        "'selected:hh,superjob' for a comma-separated subset of sources."
    ),
)
@click.option(
    "--daemon",
    is_flag=True,
    default=False,
    help=(
        "Run the built-in scheduler in the foreground instead of "
        "showing the menu — replaces external cron. Which sources run "
        "and how often is controlled by schedule_enabled/"
        "interval_hours in each source's block in "
        "work_preferences.yaml."
    ),
)
def main(auto: Optional[str], daemon: bool):
    """Точка входа CrossJob-AI."""
    non_source_auto_values = {
        "all",
        "check_hh_replies",
        "check_sj_replies",
        "check_telegram_replies",
        "cleanup_hh_negotiations",
    }
    if auto is not None and not (
        auto in non_source_auto_values
        or auto in dict(ALL_SOURCES)
        or auto.startswith("selected:")
    ):
        raise click.BadOptionUsage(
            "--auto", f"Invalid value for --auto: {auto!r}"
        )
    if daemon and auto is not None:
        raise click.BadOptionUsage(
            "--daemon", "--daemon and --auto are mutually exclusive."
        )
    try:
        # Определяем и проверяем папку с данными. Мастер первого
        # запуска — только в интерактивном режиме (без --auto/--daemon,
        # чтобы не повесить cron/демон на inquirer.confirm() без stdin).
        data_folder = Path("data_folder")
        if (
            auto is None
            and not daemon
            and (
                not data_folder.exists()
                or not (data_folder / SECRETS_YAML).exists()
            )
        ):
            if not run_setup_wizard(data_folder):
                return
        secrets_file, config_file, plain_text_resume_file, output_folder = (
            FileManager.validate_data_folder(data_folder)
        )

        # Проверяем конфигурацию и секреты
        config = ConfigValidator.validate_config(config_file)

        # Готовим параметры. plain_text_resume.yaml не обязателен на
        # старте — ensure_plain_text_resume() сгенерирует его лениво,
        # только если выбран один из пунктов Generate Resume*.
        config["plainTextResumeFile"] = plain_text_resume_file
        config["outputFileDirectory"] = output_folder
        config["dataFolder"] = data_folder
        config["secretsFile"] = secrets_file
        set_llm_usage_output_folder(output_folder)
        apply_llm_provider_override(config)
        # Провайдер должен быть применён (строкой выше) до резолва
        # ключа — иначе llm_api_keys.<provider> в secrets.yaml не
        # находится, и всегда берётся общий llm_api_key.
        llm_api_key = ConfigValidator.validate_secrets(
            secrets_file, get_active_llm_provider()
        )
        set_llm_fallback_keys(
            (ConfigValidator.load_yaml(secrets_file).get("llm_api_keys")) or {}
        )
        set_llm_fallback_base_urls(
            (
                ConfigValidator.load_yaml(secrets_file).get(
                    "llm_provider_base_urls"
                )
            )
            or {}
        )

        # Позиции не заданы — один раз выводим их из resume.pdf,
        # чтобы каждый источник (HH/SuperJob/geekjob/
        # rabota.ru/Telegram) искал роли, которые реально подходят
        # этому резюме.
        resume_pdf_path = data_folder / RESUME_PDF
        if not config.get("positions") and resume_pdf_path.exists():
            config["positions"] = infer_positions_from_resume(
                resume_pdf_path, llm_api_key
            )
            logger.info(
                "No positions configured — inferred from resume: "
                f"{config['positions']}"
            )

        if auto == "headhunter":
            search_and_apply_headhunter(config, llm_api_key)
            return

        if auto == "superjob":
            search_and_apply_superjob(config, llm_api_key)
            return

        if auto == "geekjob":
            search_geekjob(config, llm_api_key)
            return

        if auto == "rabota_ru":
            search_rabota_ru(config, llm_api_key)
            return

        if auto == "telegram":
            search_telegram(config, llm_api_key)
            return

        if auto == "getmatch":
            search_getmatch(config, llm_api_key)
            return

        if auto == "linkedin":
            search_and_apply_linkedin(config, llm_api_key)
            return

        if auto == "habr_career":
            search_and_apply_habr_career(config, llm_api_key)
            return

        if auto == "all":
            run_all_sources(config, llm_api_key)
            return

        if auto is not None and auto.startswith("selected:"):
            names = [
                name.strip()
                for name in auto.removeprefix("selected:").split(",")
                if name.strip()
            ]
            run_selected_sources(names, config, llm_api_key)
            return

        if auto == "check_hh_replies":
            check_headhunter_replies(config, llm_api_key)
            return

        if auto == "cleanup_hh_negotiations":
            cleanup_headhunter_negotiations(config)
            return

        if auto == "check_sj_replies":
            check_superjob_replies(config)
            return

        if auto == "check_telegram_replies":
            check_telegram_replies(config, llm_api_key)
            return

        if daemon:
            scheduler = Scheduler(
                SCHEDULER_SOURCES, config, llm_api_key, output_folder
            )
            try:
                scheduler.run_forever()
            except KeyboardInterrupt:
                scheduler.stop()
                logger.info("Daemon stopped.")
            return

        # Интерактивный запрос действия у пользователя
        suggest_blacklist_additions(config_file, output_folder)
        selected_actions = prompt_user_action()

        # Обрабатываем выбранное действие
        handle_inquiries(selected_actions, config, llm_api_key)

    except ConfigError as ce:
        logger.error(f"Configuration error: {ce}")
        logger.error(
            "Refer to the configuration guide for troubleshooting: "
            "docs/GUIDE.md"
        )
    except FileNotFoundError as fnf:
        logger.error(f"File not found: {fnf}")
        logger.error(
            "Ensure all required files are present in the data folder."
        )
    except RuntimeError as re:
        logger.error(f"Runtime error: {re}")
        logger.debug(traceback.format_exc())
    except Exception as e:
        logger.exception(f"An unexpected error occurred: {e}")


if __name__ == "__main__":
    main()
