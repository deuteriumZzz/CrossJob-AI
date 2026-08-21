import base64
import binascii
import re
import shutil
import sys
import traceback
from pathlib import Path
from typing import Literal, Optional, Tuple

import click
import inquirer
import yaml
from pdfminer.high_level import extract_text as extract_pdf_text

from config import (
    DAILY_APPLICATION_LIMIT,
    JOB_MAX_APPLICATIONS,
    JOB_MIN_SCORE,
    JOB_SUITABILITY_SCORE,
    LINKEDIN_DAILY_APPLICATION_LIMIT,
)
from src.config_patch import set_top_level_field
from src.job_sources.applied_log import AppliedLog
from src.job_sources.apply_pacing import (
    randomized_daily_limit,
    wait_before_apply,
    wait_between_sources,
)
from src.job_sources.base import JobSource
from src.job_sources.block_detection import (
    PlatformBlockedError,
    is_still_blocked,
    mark_blocked,
)
from src.job_sources.cover_letter import generate_cover_letter_for_job
from src.job_sources.geekjob.client import GeekjobClient
from src.job_sources.geekjob.source import GeekjobSource
from src.job_sources.getmatch.client import GetMatchClient
from src.job_sources.getmatch.source import GetMatchSource
from src.job_sources.github_context import fetch_github_summary
from src.job_sources.headhunter.auth import HHAuth
from src.job_sources.headhunter.client import HeadHunterClient
from src.job_sources.headhunter.source import HeadHunterSource
from src.job_sources.job_fit import classify_fit, score_job_fit
from src.job_sources.linkedin.answerer import EasyApplyAnswerer
from src.job_sources.linkedin.auth import LinkedInSession
from src.job_sources.linkedin.easy_apply import run_easy_apply
from src.job_sources.linkedin.source import LinkedInSource
from src.job_sources.llm_usage import (
    set_output_folder as set_llm_usage_output_folder,
)
from src.job_sources.rabota_ru.client import RabotaRuClient
from src.job_sources.rabota_ru.source import RabotaRuSource
from src.job_sources.reply_answerer import (
    build_hh_resume_summary,
    build_preferences_summary,
    generate_reply,
)
from src.job_sources.reply_check import (
    print_negotiation_replies,
    print_superjob_replies,
)
from src.job_sources.resume_profile import (
    extract_plain_text_resume,
    infer_positions_from_resume,
)
from src.job_sources.superjob.auth import SuperJobAuth
from src.job_sources.superjob.client import SuperJobClient
from src.job_sources.superjob.source import SuperJobSource
from src.job_sources.telegram.client import TelegramSourceClient
from src.job_sources.telegram.source import TelegramSource
from src.job_sources.telegram_notify import notify_from_secrets
from src.job_sources.zarplata.auth import ZarplataAuth
from src.job_sources.zarplata.client import ZarplataClient
from src.job_sources.zarplata.source import ZarplataSource
from src.libs.resume_and_cover_builder import (
    ResumeFacade,
    ResumeGenerator,
    StyleManager,
)
from src.logging import logger
from src.resume_schemas.job_application_profile import JobApplicationProfile
from src.resume_schemas.resume import Resume
from src.scheduler import Scheduler
from src.utils.chrome_utils import HTML_to_PDF, init_browser
from src.utils.constants import (
    PLAIN_TEXT_RESUME_YAML,
    RESUME_PDF,
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
    def validate_secrets(secrets_yaml_path: Path) -> str:
        """Падает сразу, если ключа LLM нет или он пустой — вместо
        непонятного 401 где-то посреди прогона."""
        secrets = ConfigValidator.load_yaml(secrets_yaml_path)
        mandatory_secrets = ["llm_api_key"]

        for secret in mandatory_secrets:
            if secret not in secrets:
                raise ConfigError(
                    f"Missing secret '{secret}' in {secrets_yaml_path}"
                )

            if not secrets[secret]:
                raise ConfigError(
                    f"Secret '{secret}' cannot be empty in {secrets_yaml_path}"
                )

        return secrets["llm_api_key"]


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


def _daily_limit(parameters: dict) -> int:
    """Дневной лимит откликов (HH/SuperJob/Zarplata) — переопределяется
    через limits.daily_application_limit в work_preferences.yaml
    (дашборд: панель "Лимиты откликов"), иначе
    config.DAILY_APPLICATION_LIMIT."""
    return int(
        (parameters.get("limits") or {}).get(
            "daily_application_limit", DAILY_APPLICATION_LIMIT
        )
    )


def _linkedin_daily_limit(parameters: dict) -> int:
    """Отдельный дневной лимит для LinkedIn — см. _daily_limit()."""
    return int(
        (parameters.get("limits") or {}).get(
            "linkedin_daily_application_limit",
            LINKEDIN_DAILY_APPLICATION_LIMIT,
        )
    )


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


def search_and_apply_headhunter(parameters: dict, llm_api_key: str):
    """
    Ищет на HeadHunter вакансии по work_preferences.yaml, пишет
    под каждую персональное сопроводительное письмо на основе
    data_folder/resume.pdf и либо откликается (при
    headhunter.auto_apply: true), либо просто логирует и
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
    hh_secrets = secrets.get("headhunter") or {}
    client_id = hh_secrets.get("client_id")
    client_secret = hh_secrets.get("client_secret")
    if not client_id or not client_secret:
        raise ConfigError(
            "Missing headhunter.client_id/client_secret in secrets.yaml"
        )

    hh_preferences = parameters.get("headhunter") or {}
    auto_apply = bool(hh_preferences.get("auto_apply", False))
    resume_id = hh_preferences.get("resume_id")
    if auto_apply and not resume_id:
        raise ConfigError(
            "headhunter.resume_id is required in "
            "work_preferences.yaml when auto_apply is true"
        )

    output_folder: Path = parameters["outputFileDirectory"]
    auth = HHAuth(client_id, client_secret, output_folder / ".hh_token.json")
    client = HeadHunterClient(auth.get_access_token())
    applied_log = AppliedLog(output_folder / "applied_log.json")

    source: JobSource = HeadHunterSource(client)
    jobs = source.search(parameters)
    logger.info(f"Found {len(jobs)} matching HeadHunter vacancies.")

    daily_limit = randomized_daily_limit(_daily_limit(parameters))
    sent_count = 0
    job_max_applications = _job_max_applications(parameters, "headhunter")
    for job in jobs:
        if sent_count >= job_max_applications:
            logger.info(
                f"Reached JOB_MAX_APPLICATIONS "
                f"({job_max_applications}) for this run."
            )
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
        tier = classify_fit(fit.score, JOB_MIN_SCORE, JOB_SUITABILITY_SCORE)
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
            client.apply(job.external_id, resume_id or "", cover_letter)
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
    if auto_apply and not resume_id:
        raise ConfigError(
            "superjob.resume_id is required in "
            "work_preferences.yaml when auto_apply is true"
        )

    output_folder: Path = parameters["outputFileDirectory"]
    auth = SuperJobAuth(
        client_id, client_secret, output_folder / ".superjob_token.json"
    )
    client = SuperJobClient(auth.get_access_token(), client_secret)
    applied_log = AppliedLog(output_folder / "applied_log.json")

    source: JobSource = SuperJobSource(client)
    jobs = source.search(parameters)
    logger.info(f"Found {len(jobs)} matching SuperJob vacancies.")

    daily_limit = randomized_daily_limit(_daily_limit(parameters))
    sent_count = 0
    job_max_applications = _job_max_applications(parameters, "superjob")
    for job in jobs:
        if sent_count >= job_max_applications:
            logger.info(
                f"Reached JOB_MAX_APPLICATIONS "
                f"({job_max_applications}) for this run."
            )
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
        tier = classify_fit(fit.score, JOB_MIN_SCORE, JOB_SUITABILITY_SCORE)
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


def search_and_apply_zarplata(parameters: dict, llm_api_key: str):
    """
    Ищет на zarplata.ru вакансии по work_preferences.yaml, пишет
    под каждую персональное сопроводительное письмо на основе
    data_folder/resume.pdf и либо откликается (при
    zarplata.auto_apply: true), либо просто логирует и
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
    zp_secrets = secrets.get("zarplata") or {}
    client_id = zp_secrets.get("client_id")
    client_secret = zp_secrets.get("client_secret")
    if not client_id or not client_secret:
        raise ConfigError(
            "Missing zarplata.client_id/client_secret in secrets.yaml"
        )

    zp_preferences = parameters.get("zarplata") or {}
    auto_apply = bool(zp_preferences.get("auto_apply", False))
    resume_id = zp_preferences.get("resume_id")
    if auto_apply and not resume_id:
        raise ConfigError(
            "zarplata.resume_id is required in "
            "work_preferences.yaml when auto_apply is true"
        )

    output_folder: Path = parameters["outputFileDirectory"]
    auth = ZarplataAuth(
        client_id, client_secret, output_folder / ".zarplata_token.json"
    )
    client = ZarplataClient(auth.get_access_token())
    applied_log = AppliedLog(output_folder / "applied_log.json")

    source: JobSource = ZarplataSource(client)
    jobs = source.search(parameters)
    logger.info(f"Found {len(jobs)} matching zarplata.ru vacancies.")

    daily_limit = randomized_daily_limit(_daily_limit(parameters))
    sent_count = 0
    job_max_applications = _job_max_applications(parameters, "zarplata")
    for job in jobs:
        if sent_count >= job_max_applications:
            logger.info(
                f"Reached JOB_MAX_APPLICATIONS "
                f"({job_max_applications}) for this run."
            )
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
        tier = classify_fit(fit.score, JOB_MIN_SCORE, JOB_SUITABILITY_SCORE)
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
            client.apply(job.external_id, resume_id or "", cover_letter)
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
    Ищет на geekjob.ru вакансии по work_preferences.yaml и пишет
    под каждую сопроводительное письмо на основе
    data_folder/resume.pdf, готовое вставить вручную. Для geekjob
    нет автоматического отклика (почему — см. докстринг
    src/job_sources/geekjob/source.py) — каждое совпадение
    записывается как dry-run.
    """
    data_folder: Path = parameters["dataFolder"]
    resume_pdf_path = data_folder / RESUME_PDF
    if not resume_pdf_path.exists():
        raise FileNotFoundError(
            f"Resume PDF not found: {resume_pdf_path}. Place your "
            f"resume as '{RESUME_PDF}' in {data_folder}."
        )

    output_folder: Path = parameters["outputFileDirectory"]
    applied_log = AppliedLog(output_folder / "applied_log.json")

    if is_still_blocked(output_folder, "geekjob"):
        logger.warning("geekjob.ru is cooling down after a block — skipping.")
        return

    source: JobSource = GeekjobSource(GeekjobClient())
    try:
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
        if applied_log.already_applied(job):
            continue

        fit = score_job_fit(resume_pdf_path, job, llm_api_key)
        tier = classify_fit(fit.score, JOB_MIN_SCORE, JOB_SUITABILITY_SCORE)
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
        logger.info(
            f"[manual apply needed] {job.role} at {job.company} ({job.link})"
        )

        applied_log.record(
            job,
            cover_letter,
            resume_id="",
            status="dry_run",
            score=fit.score,
            gaps=fit.gaps,
        )
        sent_count += 1


def search_rabota_ru(parameters: dict, llm_api_key: str):
    """
    Ищет на rabota.ru вакансии по work_preferences.yaml и пишет
    под каждую сопроводительное письмо на основе
    data_folder/resume.pdf, готовое вставить вручную. Для rabota.ru
    нет автоматического отклика (почему — см. докстринг
    src/job_sources/rabota_ru/source.py) — каждое совпадение
    записывается как dry-run.
    """
    data_folder: Path = parameters["dataFolder"]
    resume_pdf_path = data_folder / RESUME_PDF
    if not resume_pdf_path.exists():
        raise FileNotFoundError(
            f"Resume PDF not found: {resume_pdf_path}. Place your "
            f"resume as '{RESUME_PDF}' in {data_folder}."
        )

    output_folder: Path = parameters["outputFileDirectory"]
    applied_log = AppliedLog(output_folder / "applied_log.json")

    if is_still_blocked(output_folder, "rabota_ru"):
        logger.warning("rabota.ru is cooling down after a block — skipping.")
        return

    source: JobSource = RabotaRuSource(RabotaRuClient())
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

    sent_count = 0
    job_max_applications = _job_max_applications(parameters, "rabota_ru")
    for job in jobs:
        if sent_count >= job_max_applications:
            logger.info(
                f"Reached JOB_MAX_APPLICATIONS "
                f"({job_max_applications}) for this run."
            )
            break
        if applied_log.already_applied(job):
            continue

        fit = score_job_fit(resume_pdf_path, job, llm_api_key)
        tier = classify_fit(fit.score, JOB_MIN_SCORE, JOB_SUITABILITY_SCORE)
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
        logger.info(
            f"[manual apply needed] {job.role} at {job.company} ({job.link})"
        )

        applied_log.record(
            job,
            cover_letter,
            resume_id="",
            status="dry_run",
            score=fit.score,
            gaps=fit.gaps,
        )
        sent_count += 1


def search_telegram(parameters: dict, llm_api_key: str):
    """
    Ищет в настроенных Telegram-каналах свежие посты по
    ключевым словам из positions в work_preferences.yaml и пишет
    под каждый сопроводительное письмо на основе
    data_folder/resume.pdf. Автоматического отклика для Telegram
    нет — там почти всегда "напиши автору в личку", а не вызов
    API — поэтому каждое совпадение записывается как dry-run,
    готовое вставить в ответ.
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

    output_folder: Path = parameters["outputFileDirectory"]
    applied_log = AppliedLog(output_folder / "applied_log.json")

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
        if applied_log.already_applied(job):
            continue

        fit = score_job_fit(resume_pdf_path, job, llm_api_key)
        tier = classify_fit(fit.score, JOB_MIN_SCORE, JOB_SUITABILITY_SCORE)
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
        logger.info(f"[manual reply needed] {job.role} ({job.link})")

        applied_log.record(
            job,
            cover_letter,
            resume_id="",
            status="dry_run",
            score=fit.score,
            gaps=fit.gaps,
        )
        sent_count += 1


def search_getmatch(parameters: dict, llm_api_key: str):
    """
    Ищет на GetMatch вакансии по work_preferences.yaml и пишет
    под каждую сопроводительное письмо на основе
    data_folder/resume.pdf, готовое вставить вручную. Для GetMatch
    нет автоматического отклика (почему — см. докстринг
    src/job_sources/getmatch/source.py) — каждое совпадение
    записывается как dry-run.
    """
    data_folder: Path = parameters["dataFolder"]
    resume_pdf_path = data_folder / RESUME_PDF
    if not resume_pdf_path.exists():
        raise FileNotFoundError(
            f"Resume PDF not found: {resume_pdf_path}. Place your "
            f"resume as '{RESUME_PDF}' in {data_folder}."
        )

    output_folder: Path = parameters["outputFileDirectory"]
    applied_log = AppliedLog(output_folder / "applied_log.json")

    if is_still_blocked(output_folder, "getmatch"):
        logger.warning("GetMatch is cooling down after a block — skipping.")
        return

    profile_dir = output_folder / ".chrome_profile_getmatch"
    source: JobSource = GetMatchSource(GetMatchClient(profile_dir))
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
        if applied_log.already_applied(job):
            continue

        fit = score_job_fit(resume_pdf_path, job, llm_api_key)
        tier = classify_fit(fit.score, JOB_MIN_SCORE, JOB_SUITABILITY_SCORE)
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
        logger.info(
            f"[manual apply needed] {job.role} at {job.company} ({job.link})"
        )

        applied_log.record(
            job,
            cover_letter,
            resume_id="",
            status="dry_run",
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
    resume.pdf как есть. Best-effort: в момент написания не было
    живого аккаунта LinkedIn, чтобы сверить разметку модалки
    Easy Apply (см. докстринг
    src/job_sources/linkedin/easy_apply.py) — нераспознанное поле
    просто пропускает эту вакансию, а не гадает. auto_apply: false
    по умолчанию независимо от того, что в итоге стоит в
    work_preferences.yaml — первый запуск всегда dry-run, чтобы
    проверить сгенерированные ответы до того, как что-то реально
    уйдёт — включайте true только после просмотра dry-run.
    """
    data_folder: Path = parameters["dataFolder"]
    resume_pdf_path = data_folder / RESUME_PDF
    if not resume_pdf_path.exists():
        raise FileNotFoundError(
            f"Resume PDF not found: {resume_pdf_path}. Place your "
            f"resume as '{RESUME_PDF}' in {data_folder}."
        )

    profile_path = data_folder / "job_application_profile.yaml"
    if not profile_path.exists():
        raise FileNotFoundError(
            f"job_application_profile.yaml not found: {profile_path}. "
            "Required for LinkedIn's screening questions "
            "(see data_folder_example/)."
        )
    profile = JobApplicationProfile(profile_path.read_text(encoding="utf-8"))

    secrets = ConfigValidator.load_yaml(parameters["secretsFile"])
    li_secrets = secrets.get("linkedin") or {}
    email = li_secrets.get("email")
    password = li_secrets.get("password")
    if not email or not password:
        raise ConfigError("Missing linkedin.email/password in secrets.yaml")

    li_preferences = parameters.get("linkedin") or {}
    auto_apply = bool(li_preferences.get("auto_apply", False))

    output_folder: Path = parameters["outputFileDirectory"]
    session = LinkedInSession(output_folder / ".linkedin_profile")
    applied_log = AppliedLog(output_folder / "applied_log.json")

    try:
        session.ensure_logged_in(email, password)
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
                fit.score, JOB_MIN_SCORE, JOB_SUITABILITY_SCORE
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
                cover_letter = generate_cover_letter_for_job(
                    resume_pdf_path, job, llm_api_key
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


ALL_SOURCES = [
    ("headhunter", search_and_apply_headhunter),
    ("superjob", search_and_apply_superjob),
    ("zarplata", search_and_apply_zarplata),
    ("geekjob", search_geekjob),
    ("rabota_ru", search_rabota_ru),
    ("telegram", search_telegram),
    ("getmatch", search_getmatch),
    ("linkedin", search_and_apply_linkedin),
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
        try:
            search_fn(parameters, llm_api_key)
        except Exception as e:
            logger.exception(f"{name} failed, continuing with the rest: {e}")
            notify(parameters, f"CrossJob-AI: {name} упал — {e}")

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


def _answer_headhunter_messages(
    parameters: dict,
    client: HeadHunterClient,
    applied_log: AppliedLog,
    llm_api_key: str,
) -> None:
    """Автоответ на сообщения работодателя в переписке HH — НЕ
    проверено на живом аккаунте (см. докстринги
    HeadHunterClient.list_negotiation_messages/
    send_negotiation_message). Выключено по умолчанию: включается
    через headhunter.auto_reply в work_preferences.yaml, как и
    остальные auto_*-флаги в проекте."""
    hh_preferences = parameters.get("headhunter") or {}
    if not hh_preferences.get("auto_reply"):
        return

    data_folder: Path = parameters["dataFolder"]
    resume_pdf_path = data_folder / RESUME_PDF
    if not resume_pdf_path.exists():
        return

    resume_id = hh_preferences.get("resume_id")
    hh_resume_summary = "Недоступно."
    if resume_id:
        try:
            hh_resume_summary = build_hh_resume_summary(
                client.get_resume(resume_id)
            )
        except Exception as e:
            logger.warning(f"Failed to fetch HH resume for context: {e}")

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

    for negotiation in client.list_negotiations():
        vacancy = negotiation.get("vacancy") or {}
        external_id = str(vacancy.get("id") or "")
        negotiation_id = str(negotiation.get("id") or "")
        if not external_id or not negotiation_id:
            continue

        entry = applied_log.find_by_source_and_external_id(
            "headhunter", external_id
        )
        if entry is None or entry["status"] != "applied":
            continue

        try:
            messages = client.list_negotiation_messages(negotiation_id)
        except Exception as e:
            logger.warning(
                f"Failed to fetch messages for {entry['company']}: {e}"
            )
            continue
        if not messages:
            continue

        last_message = messages[-1]
        message_id = str(last_message.get("id") or "")
        author_type = (last_message.get("author") or {}).get(
            "participant_type"
        )
        message_text = last_message.get("text") or ""
        if (
            not message_id
            or not message_text
            or author_type == "applicant"
            or message_id == entry.get("last_replied_message_id")
        ):
            continue

        try:
            reply_text = generate_reply(
                resume_pdf_path,
                message_text,
                entry["title"],
                entry["company"],
                preferences_summary,
                llm_api_key,
                hh_resume_summary=hh_resume_summary,
                github_summary=github_summary,
            )
            client.send_negotiation_message(negotiation_id, reply_text)
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
    Сверяет ваши реальные отклики на HeadHunter с текущим статусом
    переговоров в HH — чтобы видеть ответ работодателя, не заходя
    на hh.ru. Плюс — если headhunter.auto_reply: true — автоматически
    отвечает на новые сообщения работодателя (см.
    _answer_headhunter_messages). Внешние формы ATS, куда может вести
    ответ работодателя, эта функция не трогает; там всё вручную.
    """
    secrets = ConfigValidator.load_yaml(parameters["secretsFile"])
    hh_secrets = secrets.get("headhunter") or {}
    client_id = hh_secrets.get("client_id")
    client_secret = hh_secrets.get("client_secret")
    if not client_id or not client_secret:
        raise ConfigError(
            "Missing headhunter.client_id/client_secret in secrets.yaml"
        )

    output_folder: Path = parameters["outputFileDirectory"]
    auth = HHAuth(client_id, client_secret, output_folder / ".hh_token.json")
    client = HeadHunterClient(auth.get_access_token())
    applied_log = AppliedLog(output_folder / "applied_log.json")

    print_negotiation_replies(
        "headhunter",
        client.list_negotiations(),
        applied_log,
        on_new_reply=lambda entry, state: notify(
            parameters,
            f"Новый ответ: {entry['company']} — {entry['title']}: {state}",
        ),
    )

    _answer_headhunter_messages(parameters, client, applied_log, llm_api_key)


def check_zarplata_replies(parameters: dict):
    """То же самое, что check_headhunter_replies, только для
    zarplata.ru (та же форма переговоров группы HeadHunter)."""
    secrets = ConfigValidator.load_yaml(parameters["secretsFile"])
    zp_secrets = secrets.get("zarplata") or {}
    client_id = zp_secrets.get("client_id")
    client_secret = zp_secrets.get("client_secret")
    if not client_id or not client_secret:
        raise ConfigError(
            "Missing zarplata.client_id/client_secret in secrets.yaml"
        )

    output_folder: Path = parameters["outputFileDirectory"]
    auth = ZarplataAuth(
        client_id, client_secret, output_folder / ".zarplata_token.json"
    )
    client = ZarplataClient(auth.get_access_token())
    applied_log = AppliedLog(output_folder / "applied_log.json")

    print_negotiation_replies(
        "zarplata",
        client.list_negotiations(),
        applied_log,
        on_new_reply=lambda entry, state: notify(
            parameters,
            f"Новый ответ: {entry['company']} — {entry['title']}: {state}",
        ),
    )


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

            if "Search & Apply on Zarplata.ru" == selected_actions:
                logger.info(
                    "Searching Zarplata.ru and preparing applications..."
                )
                search_and_apply_zarplata(parameters, llm_api_key)

            if "Search on geekjob.ru (manual apply)" == selected_actions:
                logger.info("Searching geekjob.ru...")
                search_geekjob(parameters, llm_api_key)

            if "Search on rabota.ru (manual apply)" == selected_actions:
                logger.info("Searching rabota.ru...")
                search_rabota_ru(parameters, llm_api_key)

            if "Search Telegram channels (manual reply)" == selected_actions:
                logger.info("Searching Telegram channels...")
                search_telegram(parameters, llm_api_key)

            if "Search on GetMatch (manual apply)" == selected_actions:
                logger.info("Searching GetMatch...")
                search_getmatch(parameters, llm_api_key)

            if "Search & Apply on LinkedIn" == selected_actions:
                logger.info("Searching LinkedIn Easy Apply jobs...")
                search_and_apply_linkedin(parameters, llm_api_key)

            if "Search selected sources" == selected_actions:
                names = prompt_selected_sources()
                if names:
                    run_selected_sources(names, parameters, llm_api_key)
                else:
                    logger.warning("No sources selected.")

            if "Check HeadHunter replies" == selected_actions:
                check_headhunter_replies(parameters, llm_api_key)

            if "Check SuperJob replies" == selected_actions:
                check_superjob_replies(parameters)

            if "Check Zarplata replies" == selected_actions:
                check_zarplata_replies(parameters)

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
                    "Search & Apply on Zarplata.ru",
                    "Search on geekjob.ru (manual apply)",
                    "Search on rabota.ru (manual apply)",
                    "Search Telegram channels (manual reply)",
                    "Search on GetMatch (manual apply)",
                    "Search & Apply on LinkedIn",
                    "Search selected sources",
                    "Check HeadHunter replies",
                    "Check SuperJob replies",
                    "Check Zarplata replies",
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
                ("Zarplata.ru", "zarplata"),
                ("geekjob.ru (manual apply)", "geekjob"),
                ("rabota.ru (manual apply)", "rabota_ru"),
                ("Telegram channels (manual reply)", "telegram"),
                ("GetMatch (manual apply)", "getmatch"),
                (
                    "LinkedIn (experimental, not verified live)",
                    "linkedin",
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
        "one of headhunter/superjob/zarplata/geekjob/rabota_ru/telegram/"
        "getmatch/linkedin/all/check_hh_replies/check_sj_replies/"
        "check_zp_replies, or 'selected:hh,superjob' for a comma-"
        "separated subset of sources."
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
        "check_zp_replies",
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
        llm_api_key = ConfigValidator.validate_secrets(secrets_file)

        # Готовим параметры. plain_text_resume.yaml не обязателен на
        # старте — ensure_plain_text_resume() сгенерирует его лениво,
        # только если выбран один из пунктов Generate Resume*.
        config["plainTextResumeFile"] = plain_text_resume_file
        config["outputFileDirectory"] = output_folder
        config["dataFolder"] = data_folder
        config["secretsFile"] = secrets_file
        set_llm_usage_output_folder(output_folder)

        # Позиции не заданы — один раз выводим их из resume.pdf,
        # чтобы каждый источник (HH/SuperJob/Zarplata/geekjob/
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

        if auto == "zarplata":
            search_and_apply_zarplata(config, llm_api_key)
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

        if auto == "check_sj_replies":
            check_superjob_replies(config)
            return

        if auto == "check_zp_replies":
            check_zarplata_replies(config)
            return

        if daemon:
            scheduler = Scheduler(
                dict(ALL_SOURCES), config, llm_api_key, output_folder
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
