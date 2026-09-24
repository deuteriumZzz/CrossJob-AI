from __future__ import annotations

import random
import re
import sys
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import (
    APPLICATION_RETENTION_DAYS,
    DAILY_APPLICATION_LIMIT,
    JOB_MAX_APPLICATIONS,
    JOB_MIN_SCORE,
    JOB_SUITABILITY_SCORE,
    LINKEDIN_DAILY_APPLICATION_LIMIT,
    LLM_API_URL,
    LLM_MODEL,
    LLM_MODEL_TYPE,
    LOG_TO_FILE,
)
from main import (
    ALL_SOURCES,
    SCHEDULER_SOURCES,
    TELEGRAM_INTRO_TEMPLATE_DEFAULT,
    ConfigError,
    ConfigValidator,
    FileManager,
)
from main import _daily_limit as _effective_daily_limit
from main import _job_max_applications as _effective_job_max_applications
from main import _total_daily_limit as _effective_total_daily_limit
from main import append_to_company_blacklist as _append_to_blacklist
from main import (
    apply_llm_provider_override,
    block_headhunter_employer,
)
from main import HR_DRAFTS_FILE
from main import bootstrap_data_folder as _bootstrap_data_folder
from main import prefill_direct_application as _prefill_direct_application
from main import prepare_interview as _prepare_interview
from main import start_campaign_job as _start_campaign_job
from main import send_hr_draft as _send_hr_draft
from main import (
    clone_headhunter_resume,
)
from main import create_cover_letter as _create_cover_letter
from main import (
    create_headhunter_resume_draft,
)
from main import create_resume_audit as _create_resume_audit
from main import create_resume_pdf as _create_resume_pdf
from main import create_resume_pdf_job_tailored as _create_resume_tailored
from main import force_refresh_plain_text_resume as _refresh_plain_text
from main import generate_positions_from_resume as _generate_positions
from main import (
    run_selected_sources,
)
from src.config_patch import (
    set_list_field,
    set_source_field,
    set_source_list_field,
    set_top_level_field,
    unset_source_field,
)
from src.job_sources.applied_log import (
    STAGES,
    AppliedLog,
    effective_stage,
)
from src.job_sources.llm_provider import (
    PROVIDER_MODELS,
)
from src.job_sources.llm_provider import get_active_provider as _active_llm
from src.job_sources.llm_provider import (
    set_fallback_base_urls as _set_llm_fallback_base_urls,
)
from src.job_sources.llm_provider import (
    set_fallback_keys as _set_llm_fallback_keys,
)
from src.job_sources.llm_usage import (
    llm_exhausted_today,
    provider_status_snapshot,
)
from src.job_sources.llm_usage import (
    set_output_folder as set_llm_usage_output_folder,
)
from src.job_sources.llm_usage import (
    summarize_usage,
)
from src.job_sources.preferences import effective_list
from src.job_sources.telegram.client import (
    TelegramLoginSession,
    TelegramSourceClient,
    TelegramStatusClient,
)
from src.job_sources.telegram_connect import get_bot_username, wait_for_start
from src.job_sources.telegram_control import HELP_TEXT as _TELEGRAM_HELP_TEXT
from src.direct.ats import discover_ats, fetch_jobs
from src.direct.email_channel import build_message, send_email
from src.direct.companies import load_companies, save_companies
from src.direct.campaign import CampaignJob, CampaignStore, campaign_stats
from src.direct.dossier import collect_dossier
from src.direct.importer import preview as import_preview
from src.direct.importer import read_file, rows_from_table, rows_from_text
from src.job_sources.block_detection import is_still_blocked
from src.job_sources.telegram.watcher import TELEGRAM_FOLDER
from src.job_sources.telegram_notify import bot_credentials
from src.job_sources.contact_book import ContactBook
from src.job_sources.hr_replies import (
    CATEGORY_LABELS,
    DraftStore,
    generate_first_message,
)
from src.job_sources.interview_calendar import build_ics
from src.job_sources.interview_prep import evaluate_answer, generate_questions
from src.job_sources.offers import (
    add_offer,
    compare_with_market,
    load_offers,
    save_offers,
)
from src.job_sources.market_stats import (
    REGION_LABELS,
    salary_stats,
    skill_demand,
)
from src.job_sources.telegram_conversations import TelegramConversations
from src.job_sources.telegram_notify import send_notification
from src.libs.resume_and_cover_builder import StyleManager
from src.logging import logger
from src.scheduler import DEFAULT_INTERVAL_HOURS, Scheduler
from src.scheduler_state import load_state
from src.utils import autostart, daemon_service
from src.utils.constants import RESUME_PDF, RESUME_PDF_LINKEDIN, SECRETS_YAML

# В PyInstaller-сборке (desktop_app.spec) __file__ не указывает на
# реальную папку с забандленным src/webui/static — она распакована в
# sys._MEIPASS (тот же приём, что main._project_root() и другие
# места этого семейства). Ниже это только `if STATIC_DIR.exists()` —
# без фикса дашборд молча не смонтировал бы статику, без единой
# ошибки в логах: просто пустое окно.
_MEIPASS = getattr(sys, "_MEIPASS", None)
STATIC_DIR = (
    Path(_MEIPASS) / "src" / "webui" / "static"
    if _MEIPASS
    else Path(__file__).parent / "static"
)
LOG_FILE = Path("log/app.log")


class AppContext:
    """Собирает то же, что main() делает при старте (валидация
    data_folder, парсинг work_preferences.yaml/secrets.yaml) — один
    раз на процесс, переиспользуется всеми запросами и планировщиком.
    Позиции (positions) НЕ выводятся автоматически из resume.pdf
    здесь, в отличие от main() — это нужно только интерактивным
    Generate/Search-действиям, для дашборда не критично; если
    positions пуст, соответствующий источник просто ничего не найдёт,
    пока их не заполнят вручную в work_preferences.yaml."""

    def __init__(self, data_folder: Path):
        (
            self.secrets_file,
            self.config_file,
            self.plain_text_resume_file,
            self.output_folder,
        ) = FileManager.validate_data_folder(data_folder)
        self.config = ConfigValidator.validate_config(self.config_file)
        self.config["outputFileDirectory"] = self.output_folder
        self.config["dataFolder"] = data_folder
        self.config["secretsFile"] = self.secrets_file
        self.config["plainTextResumeFile"] = self.plain_text_resume_file
        set_llm_usage_output_folder(self.output_folder)
        apply_llm_provider_override(self.config)
        _set_llm_fallback_keys(
            ConfigValidator.load_yaml(self.secrets_file).get("llm_api_keys")
        )
        _set_llm_fallback_base_urls(
            ConfigValidator.load_yaml(self.secrets_file).get(
                "llm_provider_base_urls"
            )
        )
        self.llm_api_key = self._resolve_llm_api_key()
        self.applied_log = AppliedLog(self.output_folder / "applied_log.json")
        self.scheduler: Optional[Scheduler] = None
        self.scheduler_thread: Optional[threading.Thread] = None
        self.daemon_started_at: Optional[str] = None
        self.run_now_thread: Optional[threading.Thread] = None
        self.run_now_sources: list[str] = []
        self.run_now_dry_run: bool = False
        self.run_now_current_source: Optional[str] = None
        self.run_now_stop_event: Optional[threading.Event] = None
        self.generate_thread: Optional[threading.Thread] = None
        self.generate_result: dict = {}
        self.telegram_connect_thread: Optional[threading.Thread] = None
        self.telegram_connect_status: dict = {"status": "idle"}
        self.telegram_login_session: Optional[TelegramLoginSession] = None

    def reload_config(self) -> None:
        fresh = ConfigValidator.validate_config(self.config_file)
        self.config.update(fresh)
        apply_llm_provider_override(self.config)
        _set_llm_fallback_keys(
            ConfigValidator.load_yaml(self.secrets_file).get("llm_api_keys")
        )
        _set_llm_fallback_base_urls(
            ConfigValidator.load_yaml(self.secrets_file).get(
                "llm_provider_base_urls"
            )
        )
        self.llm_api_key = self._resolve_llm_api_key()

    def _resolve_llm_api_key(self) -> str:
        """Ключ для активного провайдера (llm_api_keys.<provider> в
        secrets.yaml, с падением назад на общий llm_api_key) —
        отдельная функция, не только validate_secrets(), потому что
        здесь (в отличие от CLI-старта) отсутствие ключа для только
        что выбранного в дашборде провайдера не должно ронять весь
        процесс — пользователь ещё не успел вписать ключ для него."""
        try:
            return ConfigValidator.validate_secrets(
                self.secrets_file, _active_llm()
            )
        except ConfigError:
            return ""


def _default_data_folder() -> Path:
    """Обычный `python main.py`/`uvicorn src.webui.api:app` всегда
    запускают из корня проекта (см. README) — там CWD-относительный
    "data_folder" предсказуем. У собранного PyInstaller `.app`/`.exe`
    (desktop_app.spec) это не так: Finder/двойной клик запускает
    процесс с произвольным CWD (обычно "/" — обычный пользователь
    туда даже не может писать), поэтому "data_folder" там уходил в
    случайное место при каждом запуске вместо стабильного —
    настройки/резюме/история откликов буквально терялись между
    запусками. Для собранной версии на macOS/Windows якорим на
    стандартную для ОС постоянную папку пользователя вместо CWD;
    для остального (в т.ч. Linux-сборки, которую сегодня не собирали)
    поведение не меняется — тот же Path("data_folder"), что и раньше."""
    if getattr(sys, "frozen", False):
        if sys.platform == "darwin":
            return (
                Path.home()
                / "Library"
                / "Application Support"
                / "CrossJob-AI"
                / "data_folder"
            )
        if sys.platform == "win32":
            import os

            appdata = os.environ.get("APPDATA")
            if appdata:
                return Path(appdata) / "CrossJob-AI" / "data_folder"
    return Path("data_folder")


_data_folder = _default_data_folder()
_ctx: Optional[AppContext] = None


def set_data_folder(path: Path) -> None:
    """Только для тестов — переключает, откуда get_ctx() строит
    AppContext, и сбрасывает кэш."""
    global _data_folder, _ctx
    _data_folder = path
    _ctx = None


def get_ctx() -> AppContext:
    global _ctx
    if _ctx is None:
        try:
            _ctx = AppContext(_data_folder)
            from src.utils.backup import daily_backup

            daily_backup(_ctx.output_folder)  # и без запущенного бота
        except (FileNotFoundError, ConfigError) as e:
            raise HTTPException(
                428,
                f"data_folder ещё не настроен: {e}. Используйте "
                "POST /api/setup/init или настройте data_folder "
                "вручную (см. docs/GUIDE.md).",
            )
    return _ctx


app = FastAPI(title="CrossJob-AI")


@app.get("/api/setup/status")
def get_setup_status() -> dict:
    """Не зависит от get_ctx()/AppContext — им ещё нечего строить,
    пока data_folder не настроен. Фронтенд дергает это первым делом,
    до любого другого /api/*, чтобы показать визард вместо падающего
    дашборда."""
    needs_setup = not (
        _data_folder.exists() and (_data_folder / SECRETS_YAML).exists()
    )
    return {"needs_setup": needs_setup}


class SetupInitRequest(BaseModel):
    api_key: Optional[str] = None


@app.post("/api/setup/init")
def post_setup_init(body: SetupInitRequest) -> dict:
    """Веб-эквивалент main.run_setup_wizard() — копирует data_folder
    из шаблона и опционально пишет llm_api_key, затем сбрасывает
    закэшированный AppContext, чтобы следующий запрос строил его
    заново. Площадки/резюме/провайдер LLM — по-прежнему вручную (см.
    docs/GUIDE.md), как и в CLI-визарде."""
    global _ctx
    result = _bootstrap_data_folder(_data_folder, body.api_key or None)
    _ctx = None
    try:
        get_ctx()
        result["ready"] = True
        result["error"] = None
    except HTTPException as e:
        result["ready"] = False
        result["error"] = e.detail
    return result


# Те же поля, что main.py уже требует при старте каждого источника
# (см. "Missing X.client_id/client_secret in secrets.yaml" и
# аналогичные ConfigError) — источник правды тот же, просто здесь
# это заранее показывается в дашборде, а не падает при запуске.
# None — источнику вообще не нужны секреты (скрейпинг без аккаунта,
# либо вход целиком вручную в открывшемся браузере — как headhunter,
# см. HeadHunterSession).
_CREDENTIAL_REQUIREMENTS: dict = {
    "headhunter": None,
    "geekjob": None,
    "telegram": ("api_id", "api_hash"),
    "getmatch": ("email",),
    "linkedin": None,
    "habr_career": None,
    "wellfound": None,
    "himalayas": None,
}


# Площадки, где резюме уже есть прямо в личном кабинете (getmatch
# и т.д.) не требуют локального PDF для отклика — только
# HeadHunter и LinkedIn реально читают файл из data_folder перед
# откликом (см. RESUME_PDF/RESUME_PDF_LINKEDIN в main.py). Заявлять
# "резюме не найдено" для остальных площадок было бы ложной тревогой.
_RESUME_FILENAME_BY_SOURCE = {
    "headhunter": RESUME_PDF,
    "linkedin": RESUME_PDF_LINKEDIN,
    "wellfound": RESUME_PDF_LINKEDIN,
    "himalayas": RESUME_PDF_LINKEDIN,
}


def _resume_readiness(data_folder: Path, source: str) -> Optional[dict]:
    filename = _RESUME_FILENAME_BY_SOURCE.get(source)
    if filename is None:
        return None
    if (data_folder / filename).exists():
        return {"ready": True, "filename": filename}
    # LinkedIn/wellfound/himalayas молча падают назад на resume.pdf
    # (см. соответствующие search_and_apply_* в main.py) — не ложная
    # тревога, если общий файл всё же есть, просто предупреждаем про
    # язык/локацию.
    if (
        source in ("linkedin", "wellfound", "himalayas")
        and (data_folder / RESUME_PDF).exists()
    ):
        return {
            "ready": True,
            "filename": RESUME_PDF,
            "warning": (
                f"{RESUME_PDF_LINKEDIN} не найден — используется общий "
                f"{RESUME_PDF} (проверьте язык/локацию для международных "
                "вакансий)."
            ),
        }
    return {"ready": False, "filename": filename}


# ponytail: узкий набор самых частых причин ошибки прогона (упирались
# в это вживую — Groq TPM 429 несколько раз за сессию), не общий
# парсер всех возможных исключений. Нераспознанное — просто обрезается
# до одной строки как summary, сырой текст всегда доступен целиком в
# detail (сворачиваемый <details> в дашборде), так что информация не
# теряется — ухудшается только читаемость нераспознанных случаев.
_ERROR_PATTERNS = (
    (
        ("timed out receiving message from renderer",),
        "Страница площадки не загрузилась — браузер завис на ней. Бот "
        "повторяет загрузку сам; если повторяется часто — площадка "
        "тормозит или ограничивает доступ.",
    ),
    (
        ("rate_limit_exceeded", "rate limit"),
        "Провайдер LLM временно перегружен — бот подождёт и повторит "
        "на следующем прогоне.",
    ),
    (
        # "401" только как HTTP-статус: голое "401" попадалось в
        # шестнадцатеричных адресах стека chromedriver, и зависшая
        # страница hh показывалась как "неверный API-ключ LLM".
        ("invalid_api_key", "incorrect api key", "error code: 401", "status code 401", "401 unauthorized"),
        "Провайдер LLM не принял API-ключ — проверьте его в "
        "Настройки → Провайдер LLM.",
    ),
    (
        ("insufficient_quota", "exceeded your current quota"),
        "У провайдера LLM закончилась квота/баланс — проверьте счёт "
        "или переключите провайдера в Настройках.",
    ),
    (
        ("connectionerror", "connect timeout", "connection refused"),
        "Не удалось подключиться к площадке/провайдеру — сеть или "
        "сервис недоступны, бот повторит позже.",
    ),
    (
        ("chrome instance exited", "chrome not reachable"),
        "Chrome не смог запуститься (упал при старте или завис) — "
        "бот повторит на следующем прогоне.",
    ),
    (
        ("cannot connect to chrome", "session not created"),
        "Не удалось подключиться к браузеру Chrome для этой площадки "
        "— бот повторит на следующем прогоне.",
    ),
)


def _classify_error(raw: Optional[str]) -> Optional[dict]:
    """Сырое исключение (str(e), может быть многострочным JSON от
    LLM-провайдера с внутренними org_id и ссылками на чужой биллинг)
    → короткая фраза для человека + текст целиком под сворачиваемую
    деталь. None, если ошибки не было (last_error пуст)."""
    if not raw:
        return None
    lowered = raw.lower()
    for needles, summary in _ERROR_PATTERNS:
        if any(needle in lowered for needle in needles):
            return {"summary": summary, "detail": raw}
    first_line = raw.strip().splitlines()[0]
    summary = (
        first_line if len(first_line) <= 160 else first_line[:157] + "..."
    )
    return {"summary": summary, "detail": raw}


def _readiness(secrets: dict, data_folder: Path, source: str) -> dict:
    required = _CREDENTIAL_REQUIREMENTS.get(source)
    missing: list[str] = []
    if required is not None:
        block = secrets.get(source) or {}
        missing = [field for field in required if not block.get(field)]

    resume = _resume_readiness(data_folder, source)
    ready = not missing and (resume is None or resume["ready"])
    if resume is not None and not resume["ready"]:
        missing = [*missing, f"{resume['filename']} в data_folder"]
    return {"ready": ready, "missing": missing, "resume": resume}


@app.get("/api/status")
def get_status(ctx: AppContext = Depends(get_ctx)) -> dict:
    state = load_state(ctx.output_folder)
    secrets = ConfigValidator.load_yaml(ctx.secrets_file)
    sources = []
    for name, _ in ALL_SOURCES:
        source_config = ctx.config.get(name) or {}
        entry = state.get(name) or {}
        sources.append(
            {
                "name": name,
                "schedule_enabled": bool(
                    source_config.get("schedule_enabled")
                ),
                "auto_apply": bool(source_config.get("auto_apply")),
                # Только у telegram (auto_message) — остальные площадки
                # ключа не имеют, будет False, безвредно. Фронтенд
                # использует это + auto_apply, чтобы показать "только
                # поиск" вместо счётчика откликов там, где ничего не
                # отправляется (см. app.js source-grid).
                "auto_message": bool(source_config.get("auto_message")),
                # auto_reply/auto_bump_resume — HH-специфичные флаги
                # (чат-автоответ/бамп резюме), но приходят для каждого
                # источника: для остальных площадок просто останутся
                # false, фронтенд их там и не показывает (см. app.js).
                "auto_reply": bool(source_config.get("auto_reply")),
                "auto_bump_resume": bool(
                    source_config.get("auto_bump_resume")
                ),
                "resume_id": source_config.get("resume_id") or "",
                "interval_hours": source_config.get(
                    "interval_hours", DEFAULT_INTERVAL_HOURS
                ),
                # Свои positions/locations площадки (пусто — используется
                # общий список из панели "Поиск") + что реально ищется
                # прямо сейчас с учётом фолбэка — для панели "Фильтры"
                # в дашборде (см. effective_list).
                "positions_override": source_config.get("positions") or [],
                "locations_override": source_config.get("locations") or [],
                "effective_positions": effective_list(
                    ctx.config, name, "positions"
                ),
                "effective_locations": effective_list(
                    ctx.config, name, "locations"
                ),
                "last_run": entry.get("last_run"),
                "next_run": entry.get("next_run"),
                "status": entry.get("status", "never_run"),
                "last_error": _classify_error(entry.get("last_error")),
                "applied_today": ctx.applied_log.applied_today_count(name),
                "daily_limit": _effective_daily_limit(ctx.config, name),
                "job_max_applications": _effective_job_max_applications(
                    ctx.config, name
                ),
                # True — площадка хранит своё явное значение (см.
                # override-чекбоксы в таблице настроек); False —
                # число выше вычислено из общего дефолта
                # (limits.daily_application_limit/job_max_applications)
                # и меняется вместе с ним.
                "daily_limit_override": "daily_application_limit"
                in source_config,
                "job_max_applications_override": "job_max_applications"
                in source_config,
                "readiness": _readiness(
                    secrets, ctx.config["dataFolder"], name
                ),
            }
        )
    # Проверки чата/ответов — НЕ "площадка" (нет поиска/отклика), а
    # отдельное расписание поверх уже отправленных откликов/сообщений
    # (см. SCHEDULER_SOURCES в main.py). Раньше не было видно в
    # дашборде вообще — только правкой YAML — из-за чего непонятно,
    # включена ли реально проверка чата HH или нет.
    chat_checks: list[dict[str, Any]] = [
        {
            "name": "check_hh_replies",
            "label": "HeadHunter — статусы откликов и чат",
            "note": (
                "Приглашения/отказы → «Входящие». Автоответ в чате — "
                "если включён headhunter.auto_reply."
            ),
        },
        {
            "name": "check_telegram_replies",
            "label": "Telegram — ответы HR в диалогах",
            "note": (
                "Разбирает ответ (интерес/вопрос/отказ), готовит черновик "
                "ответа во «Входящие»."
            ),
        },
        {
            "name": "check_email_replies",
            "label": "Почта — ответы на письма HR",
            "note": "Нужна подключённая почта: Настройки → Контакты и письма.",
        },
        {
            "name": "check_telegram_commands",
            "label": "Telegram-бот — команды и утренняя сводка",
            "note": "/status, «отправить <код>», сводка в заданный час.",
        },
    ]
    for check in chat_checks:
        source_config = ctx.config.get(check["name"]) or {}
        entry = state.get(check["name"]) or {}
        check["schedule_enabled"] = bool(source_config.get("schedule_enabled"))
        check["interval_hours"] = source_config.get(
            "interval_hours", DEFAULT_INTERVAL_HOURS
        )
        check["last_run"] = entry.get("last_run")
        check["next_run"] = entry.get("next_run")
        check["status"] = entry.get("status", "never_run")
        check["last_error"] = _classify_error(entry.get("last_error"))

    daemon_running = (
        ctx.scheduler_thread is not None and ctx.scheduler_thread.is_alive()
    )
    return {
        "daemon_running": daemon_running,
        "daemon_started_at": ctx.daemon_started_at if daemon_running else None,
        "daemon_paused": bool(
            daemon_running
            and ctx.scheduler is not None
            and ctx.scheduler.paused
        ),
        "sources": sources,
        "chat_checks": chat_checks,
        "total_applied_today": ctx.applied_log.applied_today_count_all(),
        "total_daily_limit": _effective_total_daily_limit(ctx.config),
    }


@app.get("/api/stats")
def get_stats(ctx: AppContext = Depends(get_ctx)) -> dict:
    return {
        "day": ctx.applied_log.count_in_period("day"),
        "week": ctx.applied_log.count_in_period("week"),
        "month": ctx.applied_log.count_in_period("month"),
    }


@app.get("/api/results")
def get_results(ctx: AppContext = Depends(get_ctx)) -> dict:
    """Главная цифра — ответы и интервью за 7 дней (и прошлые 7 для
    сравнения) по источникам: площадки, Telegram, рассылка по почте.
    Время ответа — когда сменился этап/статус заявки."""
    from datetime import timedelta

    now = datetime.now().astimezone()
    week, prev = now - timedelta(days=7), now - timedelta(days=14)
    by_source: dict[str, dict] = {}
    totals = {"week": {"applied": 0, "replies": 0, "interviews": 0},
              "prev": {"applied": 0, "replies": 0, "interviews": 0}}

    def add(source: str, kind: str, at: str) -> None:
        when = datetime.fromisoformat(at)
        period = "week" if when >= week else "prev" if when >= prev else None
        if period is None:
            return
        totals[period][kind] += 1
        if period == "week":
            row = by_source.setdefault(source, {"source": source, "applied": 0, "replies": 0, "interviews": 0})
            row[kind] += 1

    for e in ctx.applied_log.find_by_company(""):
        if e["status"] == "applied":
            add(e["source"], "applied", e["applied_at"])
        stage = effective_stage(e)
        if stage in ("replied", "interview", "offer"):
            at = e.get("stage_at") or e.get("state_at") or e["applied_at"]
            add(e["source"], "replies", at)
            if stage in ("interview", "offer"):
                add(e["source"], "interviews", at)
    for campaign in CampaignStore(ctx.output_folder).all().values():
        for item in campaign["items"].values():
            if item.get("sent_at"):
                add("email_campaign", "applied", item["sent_at"])
            if item["status"] == "replied" and item.get("replied_at"):
                add("email_campaign", "replies", item["replied_at"])
    return {
        **totals,
        "by_source": sorted(by_source.values(), key=lambda r: (-r["replies"], -r["applied"])),
    }


@app.get("/api/export/applied-log")
def get_export_applied_log(
    ctx: AppContext = Depends(get_ctx),
) -> FileResponse:
    """Бэкап сырого applied_log.json (не HTML-отчёт и не TXT/PDF-экспорт
    из меню — тот же самый файл, что бот использует для дедупликации
    по вакансиям, на случай если его нужно сохранить/перенести."""
    if not ctx.applied_log.path.exists():
        raise HTTPException(404, "applied_log.json ещё не создан.")
    today = datetime.now().strftime("%Y-%m-%d")
    return FileResponse(
        ctx.applied_log.path,
        filename=f"applied_log_backup_{today}.json",
        media_type="application/json",
    )


@app.get("/api/applications")
def get_applications(
    source: Optional[str] = None,
    status: Optional[str] = None,
    q: str = "",
    ctx: AppContext = Depends(get_ctx),
) -> list[dict]:
    entries = ctx.applied_log.find_by_company(q)
    if source:
        entries = [e for e in entries if e["source"] == source]
    if status:
        entries = [e for e in entries if e["status"] == status]
    return [{**e, "effective_stage": effective_stage(e)} for e in entries]


class StageUpdate(BaseModel):
    source: str
    external_id: str
    stage: str = ""  # "" — снять ручную отметку


@app.post("/api/applications/stage")
def post_application_stage(
    body: StageUpdate, ctx: AppContext = Depends(get_ctx)
) -> dict:
    if body.stage and body.stage not in STAGES:
        raise HTTPException(status_code=400, detail="Неизвестный этап")
    found = ctx.applied_log.set_stage(
        body.source, body.external_id, body.stage or None
    )
    if not found:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    return {"ok": True}


@app.get("/api/replies")
def get_replies(ctx: AppContext = Depends(get_ctx)) -> list[dict]:
    entries = [
        e
        for e in ctx.applied_log.find_by_company("")
        if e.get("last_known_state")
    ]
    return sorted(entries, key=lambda e: e["applied_at"], reverse=True)


@app.get("/api/inbox")
def get_inbox(ctx: AppContext = Depends(get_ctx)) -> list[dict]:
    """Единые "Входящие": ответы hh (статус переговоров) и Telegram-
    диалоги, где HR хоть раз ответил, — одним списком, новые сверху."""
    applications = ctx.applied_log.find_by_company("")
    by_link = {e["link"]: e for e in applications}
    items = [
        {
            "channel": e["source"],
            "source": e["source"],
            "external_id": e["external_id"],
            "company": e["company"],
            "title": e["title"],
            "link": e["link"],
            "text": e["last_known_state"],
            "at": e.get("state_at") or e.get("stage_at") or e["applied_at"],
            "unread": False,
            "contact": None,
            "stage": effective_stage(e),
        }
        for e in applications
        # "Просмотрен"/"не просмотрен" — не ответ, во "Входящие" не идёт.
        if effective_stage(e) is not None
    ]
    conversations = TelegramConversations(
        ctx.output_folder / "telegram_conversations.json"
    )
    draft_by_contact = {
        d["contact"]: {"code": code, **d}
        for code, d in DraftStore(ctx.output_folder / HR_DRAFTS_FILE)
        .all()
        .items()
    }
    for conv in conversations.all():
        inbound = [m for m in conv["messages"] if m["direction"] == "in"]
        draft = draft_by_contact.get(conv["contact"])
        if not inbound and not draft:
            continue
        job_link = next(
            (m.get("job_link") for m in conv["messages"] if m.get("job_link")),
            "",
        )
        entry = by_link.get(job_link) or {}
        items.append(
            {
                "channel": "telegram_dm",
                "source": entry.get("source", "telegram"),
                "external_id": entry.get("external_id"),
                "company": entry.get("company", ""),
                "title": entry.get("title", ""),
                "link": job_link,
                "text": (
                    inbound[-1]["text"]
                    if inbound
                    else "Нет ответа — предлагаю напоминание"
                ),
                "at": (inbound or conv["messages"])[-1]["at"],
                "unread": conv.get("unread", False),
                "contact": conv["contact"],
                "stage": effective_stage(entry) if entry else None,
                "label": CATEGORY_LABELS.get(conv.get("label", ""), ""),
                "draft": draft,
            }
        )
    # Ответы на письма рассылки — сам текст в Gmail, здесь ссылка на него.
    for campaign in CampaignStore(ctx.output_folder).all().values():
        for email, item in campaign["items"].items():
            if item["status"] != "replied":
                continue
            items.append({
                "channel": "email", "source": "email_campaign", "external_id": None,
                "company": item["company"], "title": "", "contact": email,
                "link": f"https://mail.google.com/mail/u/0/#search/from%3A{email}",
                "text": f"Ответили на письмо из рассылки «{campaign['name']}» — откройте переписку в Gmail",
                "at": item.get("replied_at") or item.get("sent_at") or campaign["created_at"],
                "unread": False, "stage": "replied",
            })
    return sorted(items, key=lambda i: i["at"], reverse=True)


class OutreachSettings(BaseModel):
    email_address: Optional[str] = None
    email_app_password: Optional[str] = None
    hunter_api_key: Optional[str] = None
    email_outreach: Optional[bool] = None
    email_daily_limit: Optional[int] = None
    follow_up_days: Optional[int] = None
    digest_enabled: Optional[bool] = None
    digest_hour: Optional[int] = None
    skip_us_only: Optional[bool] = None
    skip_europe_only: Optional[bool] = None


@app.get("/api/settings/outreach")
def get_outreach_settings(ctx: AppContext = Depends(get_ctx)) -> dict:
    """Всё про контакты HR и письма в одном месте — вместо правки
    secrets.yaml/work_preferences.yaml руками. Пароль и ключ не
    отдаются, только маска."""
    secrets = ConfigValidator.load_yaml(ctx.secrets_file)
    email = secrets.get("email") or {}
    direct = ctx.config.get("direct") or {}
    digest = ctx.config.get("digest") or {}
    excluded = ctx.config.get("excluded_remote_regions", ["us_only"])
    hunter = secrets.get("hunter_api_key") or ""
    return {
        "email_address": email.get("address") or "",
        "email_connected": bool(email.get("address") and email.get("app_password")),
        "hunter_preview": _mask_api_key(hunter) if hunter else "",
        "email_outreach": bool(direct.get("email_outreach")),
        "email_daily_limit": int(direct.get("email_daily_limit", 20)),
        "follow_up_days": int(
            (ctx.config.get("telegram") or {}).get("follow_up_days", 7)
        ),
        "digest_enabled": digest.get("enabled", True) is not False,
        "digest_hour": int(digest.get("hour", 9)),
        "skip_us_only": "us_only" in (excluded or []),
        "skip_europe_only": "europe_only" in (excluded or []),
    }


@app.post("/api/settings/outreach")
def post_outreach_settings(
    body: OutreachSettings, ctx: AppContext = Depends(get_ctx)
) -> dict:
    prefs = ctx.config_file
    if body.email_address is not None:
        set_source_field(
            ctx.secrets_file, "email", "address", body.email_address.strip(), quote=True
        )
    if body.email_app_password:
        # Пароль приложения Google показывается блоками с пробелами.
        set_source_field(
            ctx.secrets_file, "email", "app_password",
            body.email_app_password.replace(" ", ""), quote=True,
        )
    if body.hunter_api_key:
        set_top_level_field(ctx.secrets_file, "hunter_api_key", body.hunter_api_key.strip())
    if body.email_outreach is not None:
        set_source_field(prefs, "direct", "email_outreach", body.email_outreach)
    if body.email_daily_limit is not None:
        set_source_field(prefs, "direct", "email_daily_limit", max(1, body.email_daily_limit))
    if body.follow_up_days is not None:
        # Одна настройка на оба канала: Telegram-диалоги и письма.
        days = max(0, body.follow_up_days)
        set_source_field(prefs, "telegram", "follow_up_days", days)
        set_source_field(prefs, "direct", "follow_up_days", days)
    if body.digest_enabled is not None:
        set_source_field(prefs, "digest", "enabled", body.digest_enabled)
    if body.digest_hour is not None:
        set_source_field(prefs, "digest", "hour", min(23, max(0, body.digest_hour)))
    if body.skip_us_only is not None or body.skip_europe_only is not None:
        current = get_outreach_settings(ctx)
        regions = [
            region
            for region, on in (
                ("us_only", body.skip_us_only if body.skip_us_only is not None else current["skip_us_only"]),
                ("europe_only", body.skip_europe_only if body.skip_europe_only is not None else current["skip_europe_only"]),
            )
            if on
        ]
        set_list_field(prefs, "excluded_remote_regions", regions)
    ctx.reload_config()
    return get_outreach_settings(ctx)


@app.post("/api/settings/outreach/test-email")
def post_test_email(ctx: AppContext = Depends(get_ctx)) -> dict:
    """Проверка почты: вход по паролю приложения и письмо самому себе."""
    secrets = ConfigValidator.load_yaml(ctx.secrets_file)
    credentials = secrets.get("email") or {}
    if not credentials.get("address") or not credentials.get("app_password"):
        raise HTTPException(400, "Сначала укажите адрес и пароль приложения")
    try:
        send_email(
            credentials,
            build_message(
                credentials["address"],
                credentials["address"],
                "CrossJob-AI: проверка почты",
                "Почта подключена — письма HR будут уходить с этого адреса.",
            ),
        )
    except Exception as e:
        raise HTTPException(502, f"Не удалось отправить: {e}")
    return {"ok": True}


@app.get("/api/hr-drafts")
def get_hr_drafts(ctx: AppContext = Depends(get_ctx)) -> list[dict]:
    """Очередь «Ждут вашего решения»: все черновики (ответы и
    напоминания в Telegram, письма HR) с вакансией, к которой относятся."""
    by_link = {e["link"]: e for e in ctx.applied_log.find_by_company("")}
    drafts = DraftStore(ctx.output_folder / HR_DRAFTS_FILE).all()
    return sorted(
        (
            {
                "code": code,
                **draft,
                "channel": draft.get("channel", "telegram"),
                "company": by_link.get(draft["job_link"], {}).get("company", ""),
                "title": by_link.get(draft["job_link"], {}).get("title", ""),
            }
            for code, draft in drafts.items()
        ),
        key=lambda d: d["created_at"],
        reverse=True,
    )


def _backfill_contact_book(ctx: AppContext, book: ContactBook) -> None:
    """Один раз при первом открытии вкладки: контакты, найденные раньше
    (email из вакансий «Прямого поиска»), переносятся в книгу."""
    for e in ctx.applied_log.find_by_company(""):
        if e.get("contacts"):
            book.add(
                e["company"],
                [
                    {"kind": "email", "value": c, "source": "текст вакансии",
                     "source_url": e["link"]}
                    for c in e["contacts"]
                ],
                vacancy={"title": e["title"], "link": e["link"], "source": e["source"]},
            )
    if not book.path.exists():
        book._save({"companies": {}})


def _contact_status(contact: dict, conversations, entries, drafts, campaign=None) -> str:
    value = contact["value"].lower()
    if campaign and value in campaign.get("replied", ()):
        return "replied"
    if campaign and value in campaign.get("bounced", ()):
        return "bounced"
    if any(d["contact"].lower() == value for d in drafts.values()):
        return "draft"
    if campaign and value in campaign.get("sent", ()):
        return "written"
    if contact["kind"] == "telegram":
        conv = conversations.get(contact["value"])
        if conv:
            if any(m["direction"] == "in" for m in conv["messages"]):
                return "replied"
            return "written"
    if contact["kind"] == "email":
        sent = [e for e in entries if (e.get("outreach_email") or "").lower() == value]
        if any(e.get("email_replied") for e in sent):
            return "replied"
        if sent:
            return "written"
    return "new"


_STATUS_ORDER = ["new", "bounced", "draft", "written", "replied"]


def _contact_events(ctx: AppContext, conversations, entries, drafts) -> dict[str, list[dict]]:
    """История по каждому контакту (email/@ник → [{at, text}]) — для
    «последнего действия» и истории в карточке компании."""
    events: dict[str, list[dict]] = {}

    def add(value: str, at: str, text: str) -> None:
        if value and at:
            events.setdefault(value.lower(), []).append({"at": at, "text": text})

    for campaign in CampaignStore(ctx.output_folder).all().values():
        for email, item in campaign["items"].items():
            add(email, item.get("sent_at", ""), "письмо отправлено")
            add(email, item.get("followed_up_at", ""), "напоминание отправлено")
            add(email, item.get("replied_at", ""), "ответили на письмо")
            if item["status"] == "bounced":
                add(email, item.get("sent_at", ""), "письмо не дошло (возврат)")
    for draft in drafts.values():
        add(draft["contact"], draft.get("created_at", ""), "черновик ждёт отправки")
    for conv in conversations.all():
        for m in conv["messages"]:
            add(conv["contact"], m["at"], "ответ в Telegram" if m["direction"] == "in" else "написали в Telegram")
    for e in entries:
        add(e.get("outreach_email", ""), e.get("outreach_sent_at", ""), "письмо HR по вакансии")
    for history in events.values():
        history.sort(key=lambda ev: ev["at"])
    return events


def _source_kind(source: str) -> str:
    """Для фильтра и значка в базе: file / telegram / dossier / vacancy."""
    group = _source_group(source)
    return {"Telegram-каналы": "telegram", "Досье компаний": "dossier", "Тексты вакансий": "vacancy"}.get(group, "file")


@app.get("/api/contacts")
def get_contacts(ctx: AppContext = Depends(get_ctx)) -> list[dict]:
    """Вкладка «Контакты»: компании и люди, которым можно написать, со
    статусом по каждому контакту (не писали / черновик / написали /
    ответили) — статус считается из переписки и черновиков."""
    book = ContactBook(ctx.output_folder)
    if not book.path.exists():
        _backfill_contact_book(ctx, book)
    conversations = TelegramConversations(
        ctx.output_folder / "telegram_conversations.json"
    )
    entries = ctx.applied_log.find_by_company("")
    drafts = DraftStore(ctx.output_folder / HR_DRAFTS_FILE).all()
    campaigns = CampaignStore(ctx.output_folder)
    campaign = {
        "sent": campaigns.emails_with_status("sent", "failed"),
        "bounced": campaigns.emails_with_status("bounced"),
        "replied": campaigns.emails_with_status("replied"),
    }
    events = _contact_events(ctx, conversations, entries, drafts)
    cards = []
    for key, card in book.all().items():
        contacts = [
            {**c, "status": _contact_status(c, conversations, entries, drafts, campaign),
             "source_kind": _source_kind(c.get("source", ""))}
            for c in card["contacts"]
        ]
        status = max(
            (c["status"] for c in contacts), key=_STATUS_ORDER.index, default="new"
        )
        if card.get("do_not_contact"):
            status = "skip"
        history = sorted(
            [{"at": c.get("found_at", ""), "text": f"добавлен {c['value']} — {c.get('source') or 'источник не указан'}"} for c in card["contacts"]]
            + [ev for c in card["contacts"] for ev in events.get(c["value"].lower(), [])],
            key=lambda ev: ev["at"],
        )
        primary = next((c for c in contacts if c["kind"] == "email"), contacts[0] if contacts else None)
        cards.append({
            "key": key, **card, "contacts": contacts, "status": status,
            "primary": primary,
            "hr": next((c["name"] for c in contacts if c.get("name")), ""),
            "source_kinds": sorted({c["source_kind"] for c in contacts}),
            "history": history,
            "last": history[-1] if history else None,
        })
    return sorted(cards, key=lambda c: c.get("updated_at", ""), reverse=True)


class ContactsBulk(BaseModel):
    keys: list[str]
    action: str  # skip / unskip / delete


@app.post("/api/contacts/bulk")
def post_contacts_bulk(body: ContactsBulk, ctx: AppContext = Depends(get_ctx)) -> dict:
    """Действия над выбранными компаниями базы. delete возвращает
    удалённые карточки — UI может «Отменить» через /api/contacts/restore."""
    book = ContactBook(ctx.output_folder)
    if body.action in ("skip", "unskip"):
        book.update(body.keys, do_not_contact=body.action == "skip")
        return {"ok": True}
    if body.action == "delete":
        return {"removed": book.delete(body.keys)}
    raise HTTPException(400, "Неизвестное действие")


class ContactsRestore(BaseModel):
    cards: list[dict]


@app.post("/api/contacts/restore")
def post_contacts_restore(body: ContactsRestore, ctx: AppContext = Depends(get_ctx)) -> dict:
    ContactBook(ctx.output_folder).restore(body.cards)
    return {"ok": True}


_STATUS_TEXT = {
    "new": "не писали", "bounced": "возврат", "draft": "черновик",
    "written": "написали", "replied": "ответили", "skip": "не писать",
}


@app.get("/api/contacts/export")
def get_contacts_export(ctx: AppContext = Depends(get_ctx)) -> Response:
    """База в CSV для Excel/Google Таблиц. Те же заголовки понимает импорт —
    можно поправить в Excel и загрузить обратно."""
    import csv
    import io

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(["Компания", "Email", "Telegram", "Имя HR", "Сайт", "Упор", "Источник", "Статус", "Последнее действие", "Дата"])
    for card in get_contacts(ctx):
        by_kind = lambda kind: ", ".join(c["value"] for c in card["contacts"] if c["kind"] == kind)  # noqa: E731
        last = card["last"] or {}
        writer.writerow([
            card.get("company", ""), by_kind("email"), by_kind("telegram"), card["hr"],
            card.get("website", ""), card.get("emphasis", ""),
            "; ".join(sorted({c.get("source", "") for c in card["contacts"]})),
            _STATUS_TEXT.get(card["status"], card["status"]), last.get("text", ""), (last.get("at") or "")[:10],
        ])
    name = f"crossjob-companies-{datetime.now().strftime('%Y-%m-%d')}.csv"
    # utf-8-sig — чтобы Excel открыл кириллицу без «кракозябр».
    return Response(
        buf.getvalue().encode("utf-8-sig"), media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={name}"},
    )


class DossierRequest(BaseModel):
    key: str
    website: str = ""


@app.post("/api/contacts/dossier")
def post_contact_dossier(
    body: DossierRequest, ctx: AppContext = Depends(get_ctx)
) -> dict:
    """Досье компании: контакты со страниц её сайта и из Hunter — сразу
    в карточку. website — если сайт ещё не известен (вводится в карточке)."""
    book = ContactBook(ctx.output_folder)
    card = book.get(body.key)
    if card is None:
        raise HTTPException(404, "Компания не найдена")
    if body.website.strip():
        card = {**card, "website": body.website.strip()}
    hunter = ConfigValidator.load_yaml(ctx.secrets_file).get("hunter_api_key") or ""
    dossier = collect_dossier(card, hunter)
    if not dossier["website"]:
        raise HTTPException(
            404, "Сайт компании не найден — укажите его в карточке и повторите."
        )
    before = len(card["contacts"])
    book.add(card["company"], dossier["contacts"], website=dossier["website"])
    after = len((book.get(body.key) or card)["contacts"])
    return {"website": dossier["website"], "added": after - before}


def _plural(n: int, one: str, few: str, many: str) -> str:
    """Слово под число (1 ответ, 2 ответа, 5 ответов) — число пишет UI."""
    n = abs(n) % 100
    if 10 < n < 20:
        return many
    return one if n % 10 == 1 else few if 2 <= n % 10 <= 4 else many


@app.get("/api/todo")
def get_todo(ctx: AppContext = Depends(get_ctx)) -> dict:
    """«Что сделать сейчас» на Главной: только то, что ждёт человека,
    каждое — со ссылкой на нужный подраздел. Пустой список = бот
    справляется сам."""
    from datetime import timedelta

    items: list[dict] = []
    drafts = DraftStore(ctx.output_folder / HR_DRAFTS_FILE).all()
    if drafts:
        items.append({
            "id": "drafts", "count": len(drafts), "view": "replies",
            "text": _plural(len(drafts), "сообщение HR ждёт", "сообщения HR ждут", "сообщений HR ждут") + " вашего «Отправить»",
        })
    since = datetime.now().astimezone() - timedelta(days=3)
    entries = ctx.applied_log.find_by_company("")
    fresh = [
        e for e in entries
        if effective_stage(e) in ("replied", "interview", "offer")
        and datetime.fromisoformat(e.get("state_at") or e.get("stage_at") or e["applied_at"]) >= since
    ]
    unread = [
        c for c in TelegramConversations(
            ctx.output_folder / "telegram_conversations.json"
        ).all()
        if c.get("unread")
    ]
    if fresh or unread:
        items.append({
            "id": "replies", "count": len(fresh) + len(unread), "view": "replies",
            "text": _plural(len(fresh) + len(unread), "новый ответ", "новых ответа", "новых ответов") + " от работодателей за 3 дня",
        })
    interviews = [e for e in entries if effective_stage(e) == "interview"]
    if interviews:
        items.append({
            "id": "interviews", "count": len(interviews), "view": "history",
            "text": _plural(len(interviews), "интервью", "интервью", "интервью") + " — подготовьтесь: «Действия» → подготовка и тренажёр",
        })
    new_contacts = [
        c for c in get_contacts(ctx) if c["status"] == "new" and c["contacts"]
    ]
    if new_contacts:
        items.append({
            "id": "contacts", "count": len(new_contacts), "view": "contacts",
            "text": _plural(len(new_contacts), "компания с контактом HR, которой", "компании с контактом HR, которым", "компаний с контактом HR, которым") + " вы ещё не писали",
        })
    paused = [
        name for name, _ in ALL_SOURCES
        if is_still_blocked(ctx.output_folder, name)
    ]
    if paused:
        items.append({
            "id": "paused", "count": len(paused), "view": "overview",
            "text": _plural(len(paused), "площадка на паузе", "площадки на паузе", "площадок на паузе") + " после капчи/блокировки: " + ", ".join(paused)
            + " — пройдите капчу в браузере и отправьте боту /resume <площадка>",
        })
    return {
        "items": items,
        "setup": _setup_checklist(ctx),
        "badges": {
            "replies": len(drafts),
            "contacts": len(new_contacts),
        },
    }


def _setup_checklist(ctx: AppContext) -> list[dict]:
    """«Готовность» на Главной: что подключено и куда нажать, если нет.
    goto — подраздел дашборда или вкладка настроек (settings-*).
    Только дешёвые проверки (файлы/ключи) — Главная обновляется часто."""
    from src.job_sources.telegram.watcher import active_watcher

    secrets = ConfigValidator.load_yaml(ctx.secrets_file)
    data_folder: Path = ctx.config["dataFolder"]
    telegram = ctx.config.get("telegram") or {}
    tg_logged_in = (ctx.output_folder / ".telegram_session.session").exists()
    profile_file = data_folder / "job_application_profile.yaml"
    profile = ConfigValidator.load_yaml(profile_file) if profile_file.exists() else {}
    checks = [
        ("resume", "Резюме", (data_folder / RESUME_PDF).exists(),
         "загрузите PDF — по нему пишутся письма и отклики", "resume"),
        ("llm", "Ключ LLM", bool(ctx.llm_api_key),
         "нужен для писем и подбора вакансий", "settings-llm"),
        ("daemon", "Бот запущен", ctx.scheduler_thread is not None and ctx.scheduler_thread.is_alive(),
         "нажмите «▶ Запустить» вверху — без этого поиск и Telegram не работают", ""),
        ("bot", "Telegram-бот уведомлений", bot_credentials(ctx.config) is not None,
         "сюда приходят вакансии с кнопками и ответы HR", "settings-notifications"),
        ("schedule", "Площадки в расписании", any((ctx.config.get(n) or {}).get("schedule_enabled") for n, _ in ALL_SOURCES),
         "поставьте галочку на карточке площадки ниже", ""),
        ("salary", "Зарплатные ожидания",
         bool(ctx.config.get("salary_expectations") or (
             profile.get("salary_expectations") or {}
         ).get("salary_range_usd")),
         "нужны для подбора вакансий и ответов на анкеты", "settings-table"),
        ("gmail", "Почта Gmail", bool((secrets.get("email") or {}).get("app_password")),
         "для рассылки компаниям с резюме во вложении", "settings-outreach"),
        ("telegram", "Вход в Telegram", tg_logged_in,
         "чтобы читать каналы с вакансиями", "telegram"),
    ]
    if tg_logged_in:
        checks.append(
            ("watch", "Telegram-парсер", bool(telegram.get("watch_enabled")) and bool(telegram.get("channels")),
             "включите и добавьте каналы — вакансии будут приходить за секунды", "settings-tg-quick")
        )
    items = [
        {"id": i, "label": label, "ok": ok, "hint": "" if ok else hint, "goto": goto}
        for i, label, ok, hint, goto in checks
    ]
    watcher = active_watcher()
    if watcher is not None and not watcher.connected:
        items.append({"id": "watch_conn", "label": "Шлюз Telegram на связи", "ok": False,
                      "hint": "переподключается — подробности в «Логах»", "goto": "logs"})
    return items


class ApplicationRef(BaseModel):
    source: str
    external_id: str


@app.post("/api/contacts/from-application")
def post_contact_from_application(
    body: ApplicationRef, ctx: AppContext = Depends(get_ctx)
) -> dict:
    """«Найти HR» у любой вакансии из «Вакансий»: заводит компанию во
    вкладке «Контакты» (с этой вакансией) и сразу пробует досье. Если сайт
    компании неизвестен — карточка остаётся с полем «сайт компании»."""
    entry = _entry_or_404(ctx, body.source, body.external_id)
    if not entry["company"]:
        raise HTTPException(400, "У вакансии не указана компания")
    book = ContactBook(ctx.output_folder)
    contacts = [
        {"kind": "email", "value": c, "source": "текст вакансии", "source_url": entry["link"]}
        for c in entry.get("contacts") or []
    ]
    key = book.add(
        entry["company"],
        contacts,
        vacancy={"title": entry["title"], "link": entry["link"], "source": entry["source"]},
        website=entry.get("company_url") or "",
    )
    try:
        result = post_contact_dossier(DossierRequest(key=key), ctx)
    except HTTPException as e:
        return {"key": key, "added": 0, "message": e.detail}
    return {"key": key, "added": result["added"], "message": ""}


IMPORT_PREVIEW_FILE = ".import_preview.json"


def _written_emails(ctx: AppContext) -> set[str]:
    written = {
        (e.get("outreach_email") or "").lower()
        for e in ctx.applied_log.find_by_company("")
        if e.get("outreach_email")
    }
    return written | CampaignStore(ctx.output_folder).emails_with_status(
        "sent", "replied", "bounced"
    )


# ponytail: задачи импорта живут в памяти процесса — после перезапуска
# дашборда незаконченный разбор надо запустить заново.
IMPORT_JOBS: dict[str, dict] = {}


def _run_import(ctx: AppContext, token: str, filename: str, data: bytes) -> None:
    """Разбор файла в фоне: большой PDF идёт к LLM частями, адреса
    проверяются параллельно — дашборд при этом не замирает."""
    import json as _json

    job = IMPORT_JOBS[token]
    try:
        job["stage"] = "Читаю файл"
        table, text = read_file(filename, data)
        if table is not None:
            rows = rows_from_table(table)
        else:
            if not ctx.llm_api_key:
                raise ValueError("Для текста/PDF нужен ключ LLM — или сохраните файл как CSV/XLSX.")
            if not text.strip():
                raise ValueError("В файле нет текста (возможно, это скан) — сохраните список как CSV/XLSX.")

            def progress(done: int, total: int) -> None:
                job.update(stage="Раскладываю по компаниям", done=done, total=total)

            rows = rows_from_text(text, ctx.llm_api_key, progress)
        if not rows:
            raise ValueError("Не нашёл в файле ни компаний, ни email.")
        job.update(stage=f"Проверяю адреса ({len(rows)})", done=0, total=0)
        known = {
            c["value"].lower()
            for card in ContactBook(ctx.output_folder).all().values()
            for c in card["contacts"]
            if c["kind"] == "email"
        }
        result = import_preview(rows, known, _written_emails(ctx))
        (ctx.output_folder / IMPORT_PREVIEW_FILE).write_text(
            _json.dumps({"token": token, "filename": filename, **result}, ensure_ascii=False),
            encoding="utf-8",
        )
        job.update(state="done", stats=result["stats"], items=result["items"][:300])
    except (ValueError, KeyError, IndexError, zipfile.BadZipFile) as e:
        job.update(state="error", detail=str(e) or "Не удалось разобрать файл")
    except Exception as e:
        logger.exception("Импорт файла упал")
        job.update(state="error", detail=f"Не удалось разобрать файл: {e}")


@app.post("/api/import/preview")
async def post_import_preview(
    file: UploadFile = File(...), ctx: AppContext = Depends(get_ctx)
) -> dict:
    """Шаг 1 импорта: запустить разбор файла в фоне, ничего не сохраняя.
    Прогресс и результат — GET /api/import/preview/{token}, сохранение —
    /api/import/commit."""
    import secrets as _secrets
    import threading

    data = await file.read()
    token = _secrets.token_hex(4)
    filename = file.filename or "file.txt"
    IMPORT_JOBS[token] = {"state": "running", "stage": "Загружаю", "done": 0, "total": 0, "filename": filename}
    threading.Thread(target=_run_import, args=(ctx, token, filename, data), daemon=True).start()
    return {"token": token}


@app.get("/api/import/preview/{token}")
def get_import_preview(token: str) -> dict:
    job = IMPORT_JOBS.get(token)
    if job is None:
        raise HTTPException(404, "Разбор не найден — загрузите файл ещё раз")
    return {"token": token, **job}


class ImportCommit(BaseModel):
    token: str
    include_unverified: bool = True


@app.post("/api/import/commit")
def post_import_commit(body: ImportCommit, ctx: AppContext = Depends(get_ctx)) -> dict:
    """Шаг 2: сохранить разобранное в общую базу контактов. Адреса с
    ошибкой (нет почтового сервера, неверный формат) не добавляются."""
    import json as _json

    path = ctx.output_folder / IMPORT_PREVIEW_FILE
    try:
        saved = _json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise HTTPException(404, "Превью устарело — загрузите файл ещё раз")
    if saved.get("token") != body.token:
        raise HTTPException(409, "Превью устарело — загрузите файл ещё раз")
    book = ContactBook(ctx.output_folder)
    companies, contacts = set(), 0
    filename = saved.get("filename") or "файл"
    for item in saved["items"]:
        take_email = item["email"] and item["check"] in (
            ("ok", "unknown", "written") if body.include_unverified else ("ok", "written")
        )
        found = []
        source = f"файл {filename}, строка {item['row']}"
        if take_email:
            found.append({"kind": "email", "value": item["email"], "name": item.get("name", ""),
                          "position": item.get("position", ""), "source": source})
        if item.get("telegram"):
            found.append({"kind": "telegram", "value": item["telegram"], "name": item.get("name", ""), "source": source})
        if not item.get("company") and not found:
            continue
        key = book.add(
            item.get("company", ""), found,
            vacancy=({"title": item.get("title", ""), "link": item.get("link", ""), "source": "import"}
                     if item.get("link") else None),
            website=item.get("website", ""),
            emphasis=item.get("emphasis", ""),
        )
        if key:
            companies.add(key)
            contacts += len(found)
    path.unlink(missing_ok=True)
    return {"companies": len(companies), "contacts": contacts, "filename": filename}


def _campaign_view(ctx: AppContext, campaign: dict) -> dict:
    # Текст готовых писем — чтобы прочитать их прямо в рассылке.
    drafts = DraftStore(ctx.output_folder / HR_DRAFTS_FILE).all()
    return {
        "id": campaign["id"], "name": campaign["name"], "created_at": campaign["created_at"],
        "stats": {
            **campaign_stats(campaign),
            "followed_up": sum(1 for i in campaign["items"].values() if i.get("followed_up_at")),
        },
        "progress": CampaignJob.progress(campaign["id"]),
        "items": [
            {
                "email": email, **item,
                "subject": drafts.get(item["code"], {}).get("subject", ""),
                "text": drafts.get(item["code"], {}).get("text", ""),
                # Готовое напоминание (молчат N дней) — если его не убрали.
                "follow_up_text": drafts.get(item.get("follow_up_code", ""), {}).get("text", "")
                if not item.get("followed_up_at") else "",
            }
            for email, item in campaign["items"].items()
        ],
    }


@app.get("/api/campaigns")
def get_campaigns(ctx: AppContext = Depends(get_ctx)) -> dict:
    """Рассылки и сколько адресов из базы ещё можно в них взять."""
    in_campaigns = set().union(
        *[set(c["items"]) for c in CampaignStore(ctx.output_folder).all().values()]
    ) if CampaignStore(ctx.output_folder).all() else set()
    sources: dict[str, int] = {}
    available = 0
    for card in get_contacts(ctx):
        if card["status"] == "skip":
            continue  # «не писать» — в рассылки не попадает
        email = next(
            (c for c in card["contacts"] if c["kind"] == "email" and c["status"] == "new"
             and c["value"].lower() not in in_campaigns),
            None,
        )
        if email:
            available += 1
            label = _source_group(email.get("source", ""))
            sources[label] = sources.get(label, 0) + 1
    campaigns = sorted(
        CampaignStore(ctx.output_folder).all().values(), key=lambda c: c["created_at"], reverse=True
    )
    return {
        "available": available,
        "sources": sources,
        "campaigns": [_campaign_view(ctx, c) for c in campaigns],
        "email_connected": bool((ConfigValidator.load_yaml(ctx.secrets_file).get("email") or {}).get("app_password")),
    }


def _source_group(source: str) -> str:
    """Группа источника для фильтра рассылки."""
    if source.startswith("файл "):
        return source.split(",")[0]
    if source.startswith("пост в @"):
        return "Telegram-каналы"
    if source.startswith("сайт") or source.startswith("Hunter"):
        return "Досье компаний"
    return "Тексты вакансий"


class CampaignCreate(BaseModel):
    name: str = ""
    source: str = ""  # "" — все источники
    keys: list[str] = []  # выбранные в базе компании; пусто — все подходящие


@app.post("/api/campaigns")
def post_campaign(body: CampaignCreate, ctx: AppContext = Depends(get_ctx)) -> dict:
    """Новая рассылка: по одному адресу на компанию, кому ещё не писали."""
    store = CampaignStore(ctx.output_folder)
    in_campaigns = set().union(*[set(c["items"]) for c in store.all().values()]) if store.all() else set()
    targets = []
    for card in get_contacts(ctx):
        if card["status"] == "skip":
            continue  # «не писать» — в рассылки не попадает
        email = next(
            (c for c in card["contacts"] if c["kind"] == "email" and c["status"] == "new"
             and c["value"].lower() not in in_campaigns
             and (not body.source or _source_group(c.get("source", "")) == body.source)),
            None,
        )
        if email and (not body.keys or card["key"] in body.keys):
            targets.append({"key": card["key"], "email": email["value"], "company": card["company"] or email["value"]})
    if not targets:
        raise HTTPException(400, "Среди выбранных нет компаний с email, которым вы ещё не писали" if body.keys
                            else "Нет компаний с email, которым вы ещё не писали")
    label = f"Выбранные ({len(targets)})" if body.keys else body.source or "Все источники"
    name = body.name.strip() or f"{label} — {datetime.now().strftime('%d.%m %H:%M')}"
    return _campaign_view(ctx, store.get(store.create(name, targets)))


class CampaignRun(BaseModel):
    resume: str = ""  # имя PDF из data_folder/telegram или "" — основное резюме


@app.post("/api/campaigns/{campaign_id}/{action}")
def post_campaign_action(
    campaign_id: str, action: str, body: CampaignRun = CampaignRun(), ctx: AppContext = Depends(get_ctx)
) -> dict:
    """prepare — написать письма; send — отправить черновики; stop."""
    store = CampaignStore(ctx.output_folder)
    if store.get(campaign_id) is None:
        raise HTTPException(404, "Рассылка не найдена")
    if action == "stop":
        job = CampaignJob.RUNNING.get(campaign_id)
        if job:
            job.stop()
        return _campaign_view(ctx, store.get(campaign_id))
    if CampaignJob.RUNNING.get(campaign_id):
        raise HTTPException(409, "По этой рассылке уже идёт работа")
    if action == "prepare":
        if not ctx.llm_api_key:
            raise HTTPException(400, "Нужен ключ LLM (Настройки → Провайдер LLM)")
        _start_campaign_job(ctx.config, ctx.llm_api_key, campaign_id, "prepare")
    elif action == "followups":
        if not (ConfigValidator.load_yaml(ctx.secrets_file).get("email") or {}).get("app_password"):
            raise HTTPException(400, "Подключите почту: Настройки → Контакты и письма")
        _start_campaign_job(ctx.config, ctx.llm_api_key, campaign_id, "followups")
    elif action == "send":
        if not (ConfigValidator.load_yaml(ctx.secrets_file).get("email") or {}).get("app_password"):
            raise HTTPException(400, "Подключите почту: Настройки → Контакты и письма")
        resume = None
        if body.resume:
            candidate = (ctx.config["dataFolder"] / TELEGRAM_FOLDER / body.resume).resolve()
            if candidate.parent == (ctx.config["dataFolder"] / TELEGRAM_FOLDER).resolve() and candidate.exists():
                resume = candidate
        _start_campaign_job(ctx.config, ctx.llm_api_key, campaign_id, "send", resume)
    else:
        raise HTTPException(400, "Неизвестное действие")
    return _campaign_view(ctx, store.get(campaign_id))


@app.delete("/api/campaigns/{campaign_id}")
def delete_campaign(campaign_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    if CampaignJob.RUNNING.get(campaign_id):
        raise HTTPException(409, "Сначала остановите рассылку")
    store = CampaignStore(ctx.output_folder)
    campaign = store.get(campaign_id)
    if campaign:
        drafts = DraftStore(ctx.output_folder / HR_DRAFTS_FILE)
        for item in campaign["items"].values():
            if item["status"] == "draft" and item["code"]:
                drafts.remove(item["code"])
        store.delete(campaign_id)
    return {"ok": True}


class ContactDraftRequest(BaseModel):
    key: str
    kind: str
    value: str


@app.post("/api/contacts/draft")
def post_contact_draft(
    body: ContactDraftRequest, ctx: AppContext = Depends(get_ctx)
) -> dict:
    """Черновик первого сообщения этому контакту — появится во
    «Входящих» в блоке «Ждут вашего решения»."""
    if body.kind not in ("telegram", "email"):
        raise HTTPException(400, "Написать можно в Telegram или на email")
    card = ContactBook(ctx.output_folder).get(body.key)
    if card is None:
        raise HTTPException(404, "Компания не найдена")
    vacancy = card["vacancies"][-1] if card["vacancies"] else {}
    person = {}
    resume_yaml = ctx.plain_text_resume_file
    if resume_yaml and Path(resume_yaml).exists():
        import yaml as _yaml

        person = (_yaml.safe_load(Path(resume_yaml).read_text(encoding="utf-8")) or {}).get(
            "personal_information"
        ) or {}
    name = f"{person.get('name', '')} {person.get('surname', '')}".strip()
    resume = ctx.config["dataFolder"] / "resume.pdf"
    try:
        message = generate_first_message(
            resume, name, card["company"], vacancy.get("title", ""),
            vacancy.get("text", ""), body.kind, ctx.llm_api_key,
        )
    except Exception as e:
        raise HTTPException(502, f"LLM: {e}")
    extra = {"channel": "email", "subject": message["subject"]} if body.kind == "email" else {}
    code = DraftStore(ctx.output_folder / HR_DRAFTS_FILE).add(
        body.value, message["text"], "first" if body.kind == "telegram" else "email",
        vacancy.get("link", ""), **extra,
    )
    return {"code": code, "text": message["text"]}


class DraftSend(BaseModel):
    text: str = ""


@app.post("/api/hr-drafts/{code}/send")
def post_send_hr_draft(
    code: str, body: DraftSend, ctx: AppContext = Depends(get_ctx)
) -> dict:
    result = _send_hr_draft(ctx.config, code, body.text)
    if not result.startswith("Отправлено"):
        raise HTTPException(status_code=400, detail=result)
    return {"message": result}


@app.put("/api/hr-drafts/{code}")
def put_hr_draft(code: str, body: DraftSend, ctx: AppContext = Depends(get_ctx)) -> dict:
    """Правка текста черновика до отправки (письмо рассылки)."""
    if not body.text.strip() or not DraftStore(ctx.output_folder / HR_DRAFTS_FILE).update_text(code, body.text):
        raise HTTPException(status_code=404, detail="Черновик не найден")
    return {"ok": True}


@app.post("/api/hr-drafts/{code}/skip")
def post_skip_hr_draft(code: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    store = DraftStore(ctx.output_folder / HR_DRAFTS_FILE)
    draft = store.get(code) or {}
    if draft.get("campaign") and draft["kind"] != "follow_up":
        # Письмо убрали из рассылки — адрес в ней «пропущен», счётчики честные.
        CampaignStore(ctx.output_folder).update_item(draft["campaign"], draft["contact"], status="skipped")
    store.remove(code)
    return {"ok": True}


class CompanyAdd(BaseModel):
    name: str = ""
    website: str = ""
    ats: str = ""
    slug: str = ""


@app.get("/api/direct/companies")
def get_direct_companies(ctx: AppContext = Depends(get_ctx)) -> list[dict]:
    return load_companies(ctx.config["dataFolder"])


@app.post("/api/direct/companies")
def post_direct_company(
    body: CompanyAdd, ctx: AppContext = Depends(get_ctx)
) -> dict:
    """Добавляет компанию: ATS определяется по сайту (или задаётся
    явно), сразу считаем её открытые вакансии — видно, что доска
    найдена и работает."""
    ats, slug = body.ats, body.slug
    if not (ats and slug):
        if not body.website:
            raise HTTPException(400, "Укажите сайт компании или ATS+slug")
        found = discover_ats(body.website)
        if found is None:
            raise HTTPException(
                404,
                "Не нашли систему найма (Greenhouse/Lever/Ashby/Workable) на "
                "сайте — укажите ATS и slug вручную или откликайтесь на сайте.",
            )
        ats, slug = found
    company = {
        "name": body.name or slug,
        "website": body.website,
        "ats": ats,
        "slug": slug,
    }
    try:
        count = len(fetch_jobs(company))
    except Exception as e:
        raise HTTPException(502, f"Доска {ats}/{slug} не отвечает: {e}")
    data_folder = ctx.config["dataFolder"]
    companies = [
        c for c in load_companies(data_folder) if c["slug"] != slug
    ] + [company]
    save_companies(data_folder, companies)
    return {**company, "jobs": count}


@app.delete("/api/direct/companies/{slug}")
def delete_direct_company(slug: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    data_folder = ctx.config["dataFolder"]
    save_companies(
        data_folder,
        [c for c in load_companies(data_folder) if c["slug"] != slug],
    )
    return {"ok": True}


class PrepRequest(BaseModel):
    source: str
    external_id: str


@app.post("/api/applications/prep")
def post_interview_prep(
    body: PrepRequest, ctx: AppContext = Depends(get_ctx)
) -> dict:
    """Справка к интервью: готовая из журнала или новая (~20 с на LLM)."""
    entry = ctx.applied_log.find_by_source_and_external_id(
        body.source, body.external_id
    )
    if entry is None:
        raise HTTPException(404, "Заявка не найдена")
    prep = _prepare_interview(ctx.config, ctx.llm_api_key, entry)
    if not prep:
        raise HTTPException(502, "Не удалось подготовить справку (LLM)")
    return {"prep": prep}


@app.post("/api/direct/prefill")
def post_direct_prefill(
    body: PrepRequest, ctx: AppContext = Depends(get_ctx)
) -> dict:
    """Открывает окно с формой отклика и заполняет, что можно."""
    try:
        filled = _prefill_direct_application(
            ctx.config, body.source, body.external_id
        )
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"filled": filled}


def _entry_or_404(ctx: AppContext, source: str, external_id: str) -> dict:
    entry = ctx.applied_log.find_by_source_and_external_id(source, external_id)
    if entry is None:
        raise HTTPException(404, "Заявка не найдена")
    return entry


@app.get("/api/applications/ics")
def get_interview_ics(
    source: str,
    external_id: str,
    start: str,
    duration: int = 60,
    ctx: AppContext = Depends(get_ctx),
) -> Response:
    """.ics для интервью — время вводится в дашборде (datetime-local,
    локальное время машины)."""
    entry = _entry_or_404(ctx, source, external_id)
    try:
        moment = datetime.fromisoformat(start)
    except ValueError:
        raise HTTPException(400, "Неверная дата")
    if moment.tzinfo is None:
        moment = moment.astimezone()
    title = f"Интервью — {entry['company']} — {entry['title']}"
    return Response(
        build_ics(moment, title, entry["link"], entry["link"], duration),
        media_type="text/calendar",
        headers={"Content-Disposition": 'attachment; filename="interview.ics"'},
    )


@app.post("/api/interview/questions")
def post_interview_questions(
    body: PrepRequest, ctx: AppContext = Depends(get_ctx)
) -> dict:
    """Вопросы тренажёра — один раз генерируются и сохраняются."""
    entry = _entry_or_404(ctx, body.source, body.external_id)
    questions = entry.get("interview_questions")
    if not questions:
        try:
            questions = generate_questions(
                entry["title"], entry["company"], entry.get("gaps") or [],
                ctx.llm_api_key,
            )
        except Exception as e:
            raise HTTPException(502, f"LLM: {e}")
        ctx.applied_log.update_fields(
            body.source, body.external_id, interview_questions=questions
        )
    return {"questions": questions}


class AnswerCheck(BaseModel):
    source: str
    external_id: str
    question: str
    answer: str


@app.post("/api/interview/feedback")
def post_interview_feedback(
    body: AnswerCheck, ctx: AppContext = Depends(get_ctx)
) -> dict:
    entry = _entry_or_404(ctx, body.source, body.external_id)
    if not body.answer.strip():
        raise HTTPException(400, "Пустой ответ")
    data_folder = ctx.config["dataFolder"]
    resume = data_folder / "resume.pdf"
    try:
        feedback = evaluate_answer(
            resume, entry["title"], body.question, body.answer, ctx.llm_api_key
        )
    except Exception as e:
        raise HTTPException(502, f"LLM: {e}")
    return {"feedback": feedback}


class OfferAdd(BaseModel):
    company: str
    amount: int
    currency: str = "RUB"
    remote: bool = True
    notes: str = ""


@app.get("/api/offers")
def get_offers(ctx: AppContext = Depends(get_ctx)) -> list[dict]:
    market = salary_stats(ctx.applied_log.find_by_company(""))
    return compare_with_market(load_offers(ctx.output_folder), market)


@app.post("/api/offers")
def post_offer(body: OfferAdd, ctx: AppContext = Depends(get_ctx)) -> dict:
    return add_offer(ctx.output_folder, body.dict())


@app.delete("/api/offers/{offer_id}")
def delete_offer(offer_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    save_offers(
        ctx.output_folder,
        [o for o in load_offers(ctx.output_folder) if o["id"] != offer_id],
    )
    return {"ok": True}


@app.get("/api/analytics/market")
def get_market(ctx: AppContext = Depends(get_ctx)) -> dict:
    """Срез рынка по собранным вакансиям: зарплаты (все записи) и спрос
    на навыки (записи, где навыки уже извлечены) против резюме."""
    entries = ctx.applied_log.find_by_company("")
    resume_path = ctx.plain_text_resume_file
    resume_text = (
        resume_path.read_text(encoding="utf-8") if resume_path.exists() else ""
    )
    regions: dict[str, int] = {}
    for e in entries:
        if e.get("remote_region"):
            label = REGION_LABELS[e["remote_region"]]
            regions[label] = regions.get(label, 0) + 1
    return {
        "salaries": salary_stats(entries),
        "skills": skill_demand(entries, resume_text)[:20],
        "regions": regions,
    }


@app.get("/api/analytics/funnel")
def get_funnel(ctx: AppContext = Depends(get_ctx)) -> dict:
    return ctx.applied_log.funnel()


@app.get("/api/usage")
def get_usage(ctx: AppContext = Depends(get_ctx)) -> dict:
    return {
        **summarize_usage(ctx.output_folder),
        "llm_exhausted_today": llm_exhausted_today(ctx.output_folder),
    }


@app.get("/api/settings/llm/status")
def get_llm_provider_status(ctx: AppContext = Depends(get_ctx)) -> dict:
    return provider_status_snapshot(ctx.output_folder)


@app.get("/api/analytics/gaps")
def get_gaps(ctx: AppContext = Depends(get_ctx)) -> list[list]:
    return [list(item) for item in ctx.applied_log.most_common_gaps()]


@app.get("/api/analytics/blacklist-candidates")
def get_blacklist_candidates(
    ctx: AppContext = Depends(get_ctx),
) -> list[str]:
    return ctx.applied_log.suggest_blacklist_candidates()


class BlockEmployerRequest(BaseModel):
    company: str


@app.post("/api/headhunter/block-employer")
def post_block_employer(
    body: BlockEmployerRequest, ctx: AppContext = Depends(get_ctx)
) -> dict:
    """Блокирует работодателя на стороне hh.ru (серверный бан) — явное
    ручное действие пользователя из списка кандидатов в блэклист
    (get_blacklist_candidates), никогда не срабатывает автоматически.
    Открывает реальный браузер (~5-10с), поэтому фоновым потоком, тем
    же паттерном, что и /api/run-now."""

    def _run() -> None:
        block_headhunter_employer(ctx.config, body.company)

    threading.Thread(target=_run, daemon=True).start()
    return {"started": True, "company": body.company}


class CloneResumeRequest(BaseModel):
    resume_id: str


@app.post("/api/headhunter/clone-resume")
def post_clone_resume(
    body: CloneResumeRequest, ctx: AppContext = Depends(get_ctx)
) -> dict:
    """Клонирует резюме на hh.ru кликом (браузерный аналог
    hh-applicant-tool clone_resume.py). Открывает реальный браузер —
    фоновым потоком, тот же паттерн, что /api/run-now."""

    def _run() -> None:
        clone_headhunter_resume(ctx.config, body.resume_id)

    threading.Thread(target=_run, daemon=True).start()
    return {"started": True, "resume_id": body.resume_id}


@app.post("/api/headhunter/create-resume-draft")
def post_create_resume_draft(ctx: AppContext = Depends(get_ctx)) -> dict:
    """Запускает мастер создания резюме на hh.ru с предзаполненной
    должностью (см. create_headhunter_resume_draft) — черновик,
    остальное пользователь дозаполняет вручную."""

    def _run() -> None:
        create_headhunter_resume_draft(ctx.config)

    threading.Thread(target=_run, daemon=True).start()
    return {"started": True}


class BlacklistRequest(BaseModel):
    companies: list[str]


@app.post("/api/blacklist")
def post_blacklist(
    body: BlacklistRequest, ctx: AppContext = Depends(get_ctx)
) -> dict:
    if body.companies:
        _append_to_blacklist(ctx.config_file, body.companies)
        ctx.reload_config()
    return {"added": body.companies}


class SourceSettingsUpdate(BaseModel):
    source: str
    auto_apply: Optional[bool] = None
    # HH-специфичные флаги (чат-автоответ/бамп резюме на HH) — для
    # остальных площадок set_source_field их просто запишет в
    # неиспользуемый блок конфига, безвредно, тот же паттерн, что уже
    # у resume_id для нерелевантных источников.
    auto_reply: Optional[bool] = None
    auto_bump_resume: Optional[bool] = None
    schedule_enabled: Optional[bool] = None
    interval_hours: Optional[int] = None
    resume_id: Optional[str] = None
    job_max_applications: Optional[int] = None
    daily_application_limit: Optional[int] = None
    # True — снять override для этой площадки, значение выше (если
    # пришло) игнорируется, площадка возвращается к общему дефолту
    # из limits.* (см. override-чекбоксы "своё значение" в таблице
    # настроек дашборда).
    clear_job_max_applications: bool = False
    clear_daily_application_limit: bool = False
    # Свои positions/locations для этой площадки — пусто/не задано
    # означает "используй общие из панели Поиск" (см. effective_list).
    positions: Optional[list[str]] = None
    locations: Optional[list[str]] = None


@app.post("/api/settings")
def post_settings(
    body: SourceSettingsUpdate, ctx: AppContext = Depends(get_ctx)
) -> dict:
    # SCHEDULER_SOURCES ⊃ ALL_SOURCES — включает ещё check_hh_replies/
    # check_sj_replies/check_telegram_replies, у
    # которых нет своей карточки в ALL_SOURCES (это не "поиск+отклик"),
    # но schedule_enabled/interval_hours переключаются тем же способом
    # (см. панель "Проверки ответов" в дашборде).
    if body.source not in dict(SCHEDULER_SOURCES):
        raise HTTPException(400, f"Unknown source: {body.source}")
    for field in (
        "auto_apply",
        "auto_reply",
        "auto_bump_resume",
        "schedule_enabled",
        "interval_hours",
    ):
        value = getattr(body, field)
        if value is not None:
            set_source_field(ctx.config_file, body.source, field, value)

    # daily_application_limit/job_max_applications поддерживают
    # override-чекбокс в дашборде: чекбокс выключен → clear_* — поле
    # реально удаляется из блока площадки, а не просто перестаёт
    # обновляться, иначе старое явное значение продолжало бы
    # действовать в обход общего дефолта (см. unset_source_field).
    for field, clear in (
        ("daily_application_limit", body.clear_daily_application_limit),
        ("job_max_applications", body.clear_job_max_applications),
    ):
        if clear:
            unset_source_field(ctx.config_file, body.source, field)
            continue
        value = getattr(body, field)
        if value is not None:
            if value < 1:
                raise HTTPException(400, f"{field} must be >= 1")
            set_source_field(ctx.config_file, body.source, field, value)
    if body.resume_id is not None:
        # resume_id — ссылка на резюме, уже загруженное вручную на
        # самой площадке (hh.ru/superjob.ru) — бот его не
        # создаёт и не перезаписывает, только передаёт при отклике.
        # quote=True: id может содержать произвольные символы.
        set_source_field(
            ctx.config_file,
            body.source,
            "resume_id",
            body.resume_id,
            quote=True,
        )
    if body.positions is not None:
        set_source_list_field(
            ctx.config_file, body.source, "positions", body.positions
        )
    if body.locations is not None:
        set_source_list_field(
            ctx.config_file, body.source, "locations", body.locations
        )
    ctx.reload_config()
    return {"source": body.source, "updated": True}


class LimitsSettingsUpdate(BaseModel):
    daily_application_limit: Optional[int] = None
    linkedin_daily_application_limit: Optional[int] = None
    total_daily_application_limit: Optional[int] = None
    job_max_applications: Optional[int] = None
    llm_daily_cost_alert_usd: Optional[float] = None
    job_min_score: Optional[float] = None
    job_suitability_score: Optional[float] = None
    application_retention_days: Optional[int] = None


def _limits_snapshot(ctx: AppContext) -> dict:
    limits = ctx.config.get("limits") or {}
    return {
        "daily_application_limit": limits.get(
            "daily_application_limit", DAILY_APPLICATION_LIMIT
        ),
        "linkedin_daily_application_limit": limits.get(
            "linkedin_daily_application_limit",
            LINKEDIN_DAILY_APPLICATION_LIMIT,
        ),
        # None — общий лимит выключен (обратная совместимость, см.
        # main._total_daily_limit()): площадки по-прежнему считают
        # свой дневной лимит независимо, без единого бюджета на всех.
        "total_daily_application_limit": limits.get(
            "total_daily_application_limit"
        ),
        "job_max_applications": limits.get(
            "job_max_applications", JOB_MAX_APPLICATIONS
        ),
        "llm_daily_cost_alert_usd": limits.get("llm_daily_cost_alert_usd"),
        # Порог фита вакансии (score_job_fit, 0-10): ниже job_min_score
        # — skipped_low_fit, письмо не генерируется; между
        # job_min_score и job_suitability_score — weak, но отклик всё
        # равно уходит (см. main.classify_fit).
        "job_min_score": limits.get("job_min_score", JOB_MIN_SCORE),
        "job_suitability_score": limits.get(
            "job_suitability_score", JOB_SUITABILITY_SCORE
        ),
        # 0 — хранить историю откликов бессрочно (по умолчанию).
        "application_retention_days": limits.get(
            "application_retention_days", APPLICATION_RETENTION_DAYS
        ),
    }


@app.get("/api/settings/limits")
def get_limits_settings(ctx: AppContext = Depends(get_ctx)) -> dict:
    return _limits_snapshot(ctx)


@app.post("/api/settings/limits")
def post_limits_settings(
    body: LimitsSettingsUpdate, ctx: AppContext = Depends(get_ctx)
) -> dict:
    """limits — такой же плоский top-level блок в
    work_preferences.yaml, как headhunter:/superjob:, поэтому пишется
    той же текстовой правкой (set_source_field), не yaml.safe_dump
    всего файла — чтобы не терять комментарии пользователя."""
    for field in (
        "daily_application_limit",
        "linkedin_daily_application_limit",
        "total_daily_application_limit",
        "job_max_applications",
    ):
        value = getattr(body, field)
        if value is not None:
            if value < 1:
                raise HTTPException(400, f"{field} must be >= 1")
            set_source_field(ctx.config_file, "limits", field, value)

    if body.llm_daily_cost_alert_usd is not None:
        if body.llm_daily_cost_alert_usd <= 0:
            raise HTTPException(400, "llm_daily_cost_alert_usd must be > 0")
        set_source_field(
            ctx.config_file,
            "limits",
            "llm_daily_cost_alert_usd",
            body.llm_daily_cost_alert_usd,
        )

    if body.application_retention_days is not None:
        if body.application_retention_days < 0:
            raise HTTPException(400, "application_retention_days must be >= 0")
        set_source_field(
            ctx.config_file,
            "limits",
            "application_retention_days",
            body.application_retention_days,
        )

    if (
        body.job_min_score is not None
        or body.job_suitability_score is not None
    ):
        for field in ("job_min_score", "job_suitability_score"):
            value = getattr(body, field)
            if value is not None and not (0 <= value <= 10):
                raise HTTPException(400, f"{field} must be between 0 and 10")
        # Валидация ДО записи на диск — иначе при невалидном сочетании
        # (min > suitability) одно из полей уже сохранится раньше, чем
        # долетит ошибка. current — то, что уже эффективно действует
        # (ctx.config ещё не тронут set_source_field ниже), подставляем
        # его как дефолт для поля, не переданного в этом запросе.
        current = _limits_snapshot(ctx)
        min_score = (
            body.job_min_score
            if body.job_min_score is not None
            else current["job_min_score"]
        )
        suitability = (
            body.job_suitability_score
            if body.job_suitability_score is not None
            else current["job_suitability_score"]
        )
        if min_score > suitability:
            raise HTTPException(
                400, "job_min_score must not exceed job_suitability_score"
            )
        for field in ("job_min_score", "job_suitability_score"):
            value = getattr(body, field)
            if value is not None:
                set_source_field(ctx.config_file, "limits", field, value)

    ctx.reload_config()
    return _limits_snapshot(ctx)


def _distribute_total_limit(total: int, sources: list[str]) -> dict[str, int]:
    """Раскидывает total между sources случайными долями (LinkedIn и
    Himalayas — вдвое меньший вес по умолчанию, см. risk-banner в
    дашборде: банят автоматизацию агрессивнее остальных площадок,
    подтверждено вживую анти-бот интерстишлом на himalayas.app). Сумма
    долей после округления вниз почти всегда меньше total — остаток
    раздаётся по одной штуке в случайном порядке, чтобы сумма сошлась
    ровно."""
    weights = {
        s: (0.5 if s in ("linkedin", "himalayas") else 1.0)
        * random.uniform(0.6, 1.4)
        for s in sources
    }
    weight_sum = sum(weights.values())
    shares = {s: int(total * w / weight_sum) for s, w in weights.items()}
    remainder = total - sum(shares.values())
    order = list(sources)
    random.shuffle(order)
    i = 0
    while remainder > 0:
        shares[order[i % len(order)]] += 1
        remainder -= 1
        i += 1
    return shares


@app.post("/api/settings/limits/distribute")
def post_distribute_limits(ctx: AppContext = Depends(get_ctx)) -> dict:
    """Кнопка "Распределить" — то же самое, что раньше приходилось
    делать руками (вписать число в каждую строку таблицы площадок),
    одним кликом: берёт уже заданный общий дневной лимит и раскидывает
    его по площадкам в расписании (schedule_enabled), с уклоном против
    LinkedIn."""
    total = _limits_snapshot(ctx)["total_daily_application_limit"]
    if not total:
        raise HTTPException(
            400, "Сначала задайте общий дневной лимит (поле выше)."
        )
    sources = [
        name
        for name, _ in ALL_SOURCES
        if (ctx.config.get(name) or {}).get("schedule_enabled")
    ]
    if not sources:
        sources = [name for name, _ in ALL_SOURCES]
    shares = _distribute_total_limit(total, sources)
    for source, value in shares.items():
        set_source_field(
            ctx.config_file, source, "daily_application_limit", value
        )
    ctx.reload_config()
    return {"shares": shares}


_SEARCH_LIST_FIELDS = (
    "positions",
    "locations",
    "company_blacklist",
    "title_blacklist",
    "location_blacklist",
)


class SearchSettingsUpdate(BaseModel):
    positions: Optional[list[str]] = None
    locations: Optional[list[str]] = None
    company_blacklist: Optional[list[str]] = None
    title_blacklist: Optional[list[str]] = None
    location_blacklist: Optional[list[str]] = None


def _search_snapshot(ctx: AppContext) -> dict:
    return {
        field: ctx.config.get(field) or [] for field in _SEARCH_LIST_FIELDS
    }


@app.get("/api/settings/search")
def get_search_settings(ctx: AppContext = Depends(get_ctx)) -> dict:
    return _search_snapshot(ctx)


@app.post("/api/settings/search")
def post_search_settings(
    body: SearchSettingsUpdate, ctx: AppContext = Depends(get_ctx)
) -> dict:
    """positions/locations/*_blacklist — top-level списки в
    work_preferences.yaml, раньше правились только руками; пишутся
    той же текстовой техникой (set_list_field), что и остальные
    настройки дашборда, — не yaml.safe_dump всего файла, чтобы не
    терять комментарии пользователя."""
    for field in _SEARCH_LIST_FIELDS:
        value = getattr(body, field)
        if value is not None:
            set_list_field(ctx.config_file, field, value)
    ctx.reload_config()
    return _search_snapshot(ctx)


class TelegramSettingsUpdate(BaseModel):
    # Каналы живут отдельно от общих positions/locations (см.
    # _search_snapshot выше) — это не площадка поиска, а свой раздел в
    # UI, см. обсуждение "площадки это одно, а телеграм канал уже
    # другое". channels принимает как @username/username, так и полные
    # ссылки https://t.me/username — нормализуется в
    # telegram.client.normalize_channel при поиске.
    channels: Optional[list[str]] = None
    max_post_age_days: Optional[int] = None
    auto_message: Optional[bool] = None
    daily_message_limit: Optional[int] = None
    active_hours_start: Optional[int] = None
    active_hours_end: Optional[int] = None
    intro_message_template: Optional[str] = None


def _telegram_settings_snapshot(ctx: AppContext) -> dict:
    tg = ctx.config.get("telegram") or {}
    return {
        "channels": tg.get("channels") or [],
        "max_post_age_days": tg.get("max_post_age_days", 7),
        "auto_message": tg.get("auto_message", False),
        "daily_message_limit": tg.get("daily_message_limit", 15),
        "active_hours_start": tg.get("active_hours_start"),
        "active_hours_end": tg.get("active_hours_end"),
        "intro_message_template": tg.get(
            "intro_message_template", TELEGRAM_INTRO_TEMPLATE_DEFAULT
        ),
    }


@app.get("/api/settings/telegram")
def get_telegram_settings(ctx: AppContext = Depends(get_ctx)) -> dict:
    return _telegram_settings_snapshot(ctx)


@app.post("/api/settings/telegram")
def post_telegram_settings(
    body: TelegramSettingsUpdate, ctx: AppContext = Depends(get_ctx)
) -> dict:
    if body.channels is not None:
        set_source_list_field(
            ctx.config_file, "telegram", "channels", body.channels
        )
    for field in (
        "max_post_age_days",
        "auto_message",
        "daily_message_limit",
        "active_hours_start",
        "active_hours_end",
    ):
        value = getattr(body, field)
        if value is not None:
            set_source_field(ctx.config_file, "telegram", field, value)
    if body.intro_message_template is not None:
        set_source_field(
            ctx.config_file,
            "telegram",
            "intro_message_template",
            body.intro_message_template,
            quote=True,
        )
    ctx.reload_config()
    return _telegram_settings_snapshot(ctx)


class TelegramWatchUpdate(BaseModel):
    greeting: Optional[str] = None
    enabled: Optional[bool] = None
    keywords: Optional[list[str]] = None
    stop_words: Optional[list[str]] = None
    forward_to: Optional[str] = None


def _telegram_watch_snapshot(ctx: AppContext) -> dict:
    from src.job_sources.telegram.watcher import active_watcher, default_keywords

    telegram = ctx.config.get("telegram") or {}
    watcher = active_watcher()
    return {
        "enabled": bool(telegram.get("watch_enabled")),
        "keywords": telegram.get("watch_keywords") or [],
        "default_keywords": default_keywords(
            telegram.get("positions") or ctx.config.get("positions") or []
        ),
        "stop_words": telegram.get("watch_stop_words") or [],
        "forward_to": telegram.get("watch_forward_to") or "me",
        "running": watcher is not None,
        "channels": len(telegram.get("channels") or []),
        "matched": watcher.matched_count if watcher else 0,
        # Сколько контактов HR парсер уже положил в «Базу компаний».
        "contacts_collected": sum(
            1 for card in ContactBook(ctx.output_folder).all().values()
            for c in card.get("contacts") or [] if (c.get("source") or "").startswith("пост в @")
        ),
        "daemon_running": ctx.scheduler_thread is not None
        and ctx.scheduler_thread.is_alive(),
        "bot_connected": bot_credentials(ctx.config) is not None,
        "greeting": telegram.get("intro_message_template") or "",
        "resumes": _telegram_resume_list(ctx),
    }


def _telegram_resume_list(ctx: AppContext) -> list[dict]:
    folder = ctx.config["dataFolder"] / TELEGRAM_FOLDER
    own = sorted(folder.glob("*.pdf")) if folder.exists() else []
    return [{"name": p.name, "size": p.stat().st_size} for p in own]


@app.post("/api/telegram/resumes")
async def post_telegram_resume(
    file: UploadFile = File(...), ctx: AppContext = Depends(get_ctx)
) -> dict:
    """Резюме для кнопки «👋 + 📎» — сохраняется в data_folder/telegram/
    под своим именем (оно же подпись на кнопке)."""
    content = await file.read()
    if not content.startswith(b"%PDF-"):
        raise HTTPException(400, "Файл не похож на PDF.")
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(400, "Файл больше 20 МБ — Telegram такой не примет.")
    stem = re.sub(r"[^\w\-]+", "_", Path(file.filename or "resume").stem).strip("_") or "resume"
    folder = ctx.config["dataFolder"] / TELEGRAM_FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{stem[:60]}.pdf").write_bytes(content)
    return {"resumes": _telegram_resume_list(ctx)}


@app.delete("/api/telegram/resumes/{name}")
def delete_telegram_resume(name: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    folder = ctx.config["dataFolder"] / TELEGRAM_FOLDER
    target = (folder / name).resolve()
    if target.parent != folder.resolve() or target.suffix != ".pdf":
        raise HTTPException(400, "Неверное имя файла")
    target.unlink(missing_ok=True)
    return {"resumes": _telegram_resume_list(ctx)}


@app.get("/api/settings/telegram-watch")
def get_telegram_watch(ctx: AppContext = Depends(get_ctx)) -> dict:
    return _telegram_watch_snapshot(ctx)


@app.post("/api/settings/telegram-watch")
def post_telegram_watch(
    body: TelegramWatchUpdate, ctx: AppContext = Depends(get_ctx)
) -> dict:
    """Telegram-парсер. Слова применяются на ходу; включение и выключение —
    сразу, если бот запущен (иначе — при «Запустить»)."""
    prefs = ctx.config_file
    if body.enabled is not None:
        set_source_field(prefs, "telegram", "watch_enabled", body.enabled)
    if body.keywords is not None:
        set_source_list_field(
            prefs, "telegram", "watch_keywords",
            [k.strip() for k in body.keywords if k.strip()],
        )
    if body.stop_words is not None:
        set_source_list_field(
            prefs, "telegram", "watch_stop_words",
            [k.strip() for k in body.stop_words if k.strip()],
        )
    if body.forward_to is not None:
        set_source_field(
            prefs, "telegram", "watch_forward_to",
            body.forward_to.strip().lstrip("@") or "me", quote=True,
        )
    if body.greeting is not None and body.greeting.strip():
        set_source_field(
            prefs, "telegram", "intro_message_template", body.greeting.strip(), quote=True,
        )
    ctx.reload_config()
    daemon_running = ctx.scheduler_thread is not None and ctx.scheduler_thread.is_alive()
    if body.enabled is not None and daemon_running:
        from src.job_sources.telegram.watcher import active_watcher, start_telegram_watcher

        watcher = active_watcher()
        if body.enabled and watcher is None:
            start_telegram_watcher(ctx.config, ctx.llm_api_key)
        elif not body.enabled and watcher is not None:
            watcher.stop()
    return _telegram_watch_snapshot(ctx)


def _telegram_session_path(ctx: AppContext) -> Path:
    return ctx.output_folder / ".telegram_session"


def _telegram_secrets(ctx: AppContext) -> tuple[str, str] | None:
    tg_secrets = (
        ConfigValidator.load_yaml(ctx.secrets_file).get("telegram") or {}
    )
    api_id, api_hash = tg_secrets.get("api_id"), tg_secrets.get("api_hash")
    return (api_id, api_hash) if api_id and api_hash else None


@app.get("/api/telegram/status")
def get_telegram_status(ctx: AppContext = Depends(get_ctx)) -> dict:
    """Бейдж подключения в UI: настроен ли api_id/api_hash и
    авторизована ли сессия (человек уже один раз ввёл код входа) — без
    попытки залогиниться самой (см. TelegramStatusClient: connect(), а
    не start(), иначе запрос из вебui завис бы в ожидании
    интерактивного ввода, которому неоткуда прийти)."""
    from src.job_sources.telegram.watcher import active_watcher

    creds = _telegram_secrets(ctx)
    if creds is None:
        return {"configured": False, "connected": False}
    if active_watcher() is not None:
        # Парсер держит сессию открытой — значит, вход выполнен.
        return {"configured": True, "connected": True}
    try:
        with TelegramStatusClient(
            int(creds[0]), creds[1], _telegram_session_path(ctx)
        ) as client:
            connected = client.is_authorized()
    except Exception as e:
        if "locked" in str(e):
            # Сессией прямо сейчас пользуется поиск/отправка — вход есть.
            return {"configured": True, "connected": True}
        logger.warning(f"Failed to check Telegram session status: {e}")
        return {"configured": True, "connected": False}
    return {"configured": True, "connected": connected}


class TelegramLoginPhone(BaseModel):
    phone: str


class TelegramLoginCode(BaseModel):
    code: str


class TelegramLoginPassword(BaseModel):
    password: str


class TelegramKeys(BaseModel):
    api_id: str
    api_hash: str


@app.post("/api/telegram/keys")
def post_telegram_keys(body: TelegramKeys, ctx: AppContext = Depends(get_ctx)) -> dict:
    """api_id/api_hash с my.telegram.org — из дашборда, без правки
    secrets.yaml руками. Нужны один раз, дальше — вход по коду."""
    api_id, api_hash = body.api_id.strip(), body.api_hash.strip()
    if not api_id.isdigit() or not re.fullmatch(r"[0-9a-f]{32}", api_hash):
        raise HTTPException(400, "api_id — это число, api_hash — 32 символа (буквы a–f и цифры). Скопируйте их с my.telegram.org → API development tools.")
    set_source_field(ctx.secrets_file, "telegram", "api_id", int(api_id))
    set_source_field(ctx.secrets_file, "telegram", "api_hash", api_hash, quote=True)
    return {"ok": True}


@app.post("/api/telegram/login/start")
def post_telegram_login_start(
    body: TelegramLoginPhone, ctx: AppContext = Depends(get_ctx)
) -> dict:
    """Шаг 1 веб-визарда входа (вместо консольного): подключается,
    просит Telegram выслать код на указанный номер. Держит живой
    TelegramLoginSession в ctx между запросами — code/password должны
    прийти на ТОТ ЖЕ клиент, Telethon хранит phone_code_hash на нём."""
    creds = _telegram_secrets(ctx)
    if creds is None:
        raise HTTPException(
            400, "Сначала вставьте api_id и api_hash: Общение → Telegram-парсер → «Подключение аккаунта»."
        )
    if ctx.telegram_login_session is not None:
        ctx.telegram_login_session.close()
        ctx.telegram_login_session = None
    session = TelegramLoginSession(
        int(creds[0]), creds[1], _telegram_session_path(ctx)
    )
    try:
        session.send_code(body.phone.strip())
    except Exception as e:
        session.close()
        raise HTTPException(400, f"Не удалось отправить код: {e}")
    ctx.telegram_login_session = session
    return {"sent": True}


@app.post("/api/telegram/login/code")
def post_telegram_login_code(
    body: TelegramLoginCode, ctx: AppContext = Depends(get_ctx)
) -> dict:
    """Шаг 2: код, присланный Telegram. True — сразу вошли; иначе
    needs_password (включена 2FA) — фронт показывает третье поле."""
    session = ctx.telegram_login_session
    if session is None:
        raise HTTPException(400, "Сначала запросите код (шаг 1).")
    try:
        signed_in = session.submit_code(body.code.strip())
    except Exception as e:
        raise HTTPException(400, f"Неверный код: {e}")
    if signed_in:
        session.close()
        ctx.telegram_login_session = None
        return {"connected": True, "needs_password": False}
    return {"connected": False, "needs_password": True}


@app.post("/api/telegram/login/password")
def post_telegram_login_password(
    body: TelegramLoginPassword, ctx: AppContext = Depends(get_ctx)
) -> dict:
    """Шаг 3 (только если включена 2FA)."""
    session = ctx.telegram_login_session
    if session is None:
        raise HTTPException(400, "Сначала пройдите шаги 1 и 2.")
    try:
        session.submit_password(body.password)
    except Exception as e:
        raise HTTPException(400, f"Неверный пароль: {e}")
    session.close()
    ctx.telegram_login_session = None
    return {"connected": True}


class AutostartUpdate(BaseModel):
    enabled: bool


@app.get("/api/settings/autostart")
def get_autostart() -> dict:
    supported = autostart.is_supported()
    return {
        "supported": supported,
        "enabled": autostart.is_enabled() if supported else False,
    }


@app.post("/api/settings/autostart")
def post_autostart(body: AutostartUpdate) -> dict:
    if not autostart.is_supported():
        raise HTTPException(
            400, f"Автозапуск не поддерживается на {sys.platform}."
        )
    try:
        autostart.set_enabled(body.enabled)
    except Exception as e:
        raise HTTPException(500, f"Не удалось изменить автозапуск: {e}")
    return {"supported": True, "enabled": autostart.is_enabled()}


class DaemonServiceUpdate(BaseModel):
    enabled: bool


@app.get("/api/settings/daemon_service")
def get_daemon_service() -> dict:
    supported = daemon_service.is_supported()
    return {
        "supported": supported,
        "enabled": daemon_service.is_enabled() if supported else False,
    }


@app.post("/api/settings/daemon_service")
def post_daemon_service(body: DaemonServiceUpdate) -> dict:
    if not daemon_service.is_supported():
        raise HTTPException(
            400, f"Фоновый демон не поддерживается на {sys.platform}."
        )
    try:
        daemon_service.set_enabled(body.enabled)
    except Exception as e:
        raise HTTPException(500, f"Не удалось изменить фоновый демон: {e}")
    return {"supported": True, "enabled": daemon_service.is_enabled()}


@app.post("/api/telegram/login/cancel")
def post_telegram_login_cancel(ctx: AppContext = Depends(get_ctx)) -> dict:
    if ctx.telegram_login_session is not None:
        ctx.telegram_login_session.close()
        ctx.telegram_login_session = None
    return {"cancelled": True}


@app.get("/api/telegram/conversations")
def get_telegram_conversations(ctx: AppContext = Depends(get_ctx)) -> list:
    conversations = TelegramConversations(
        ctx.output_folder / "telegram_conversations.json"
    )
    return [
        {
            "contact": conv["contact"],
            "last_activity_at": conv["last_activity_at"],
            "last_message": (
                conv["messages"][-1] if conv["messages"] else None
            ),
            "message_count": len(conv["messages"]),
            "unread": conv.get("unread", False),
        }
        for conv in conversations.all()
    ]


@app.get("/api/telegram/conversations/{contact}")
def get_telegram_conversation(
    contact: str, ctx: AppContext = Depends(get_ctx)
) -> dict:
    """Открытие треда в UI автоматически гасит его "непрочитано" —
    как в любом мессенджере, отдельной кнопки "прочитано" не нужно."""
    conversations = TelegramConversations(
        ctx.output_folder / "telegram_conversations.json"
    )
    conv = conversations.get(contact)
    if conv is None:
        raise HTTPException(404, f"No conversation with @{contact}")
    if conv.get("unread"):
        conversations.mark_read(contact)
        conv = conversations.get(contact)
        if conv is None:
            raise HTTPException(404, f"No conversation with @{contact}")
    return conv


class TelegramMessageSend(BaseModel):
    text: str


@app.post("/api/telegram/conversations/{contact}/send")
def post_telegram_message(
    contact: str,
    body: TelegramMessageSend,
    ctx: AppContext = Depends(get_ctx),
) -> dict:
    """Ручная отправка из чата в дашборде — в отличие от холодного
    первого сообщения (search_telegram), это осознанное действие
    пользователя прямо сейчас, поэтому без pacing/лимитов: он и так не
    будет печатать сотню сообщений в секунду руками."""
    creds = _telegram_secrets(ctx)
    if creds is None:
        raise HTTPException(
            400, "Сначала вставьте api_id и api_hash: Общение → Telegram-парсер → «Подключение аккаунта»."
        )
    if not body.text.strip():
        raise HTTPException(400, "Message text is empty")
    try:
        with TelegramSourceClient(
            int(creds[0]), creds[1], _telegram_session_path(ctx)
        ) as client:
            client.send_message(contact, body.text)
    except Exception as e:
        raise HTTPException(502, f"Failed to send Telegram message: {e}")

    conversations = TelegramConversations(
        ctx.output_folder / "telegram_conversations.json"
    )
    conversations.record_outbound(contact, body.text)
    conv = conversations.get(contact)
    if conv is None:
        raise HTTPException(500, "Conversation vanished after send")
    return conv


@app.post("/api/telegram/conversations/{contact}/send-resume")
def post_telegram_send_resume(
    contact: str, ctx: AppContext = Depends(get_ctx)
) -> dict:
    """Кнопка "📎 Резюме" в чате — отправляет уже существующий
    data_folder/resume.pdf файлом, только по явному нажатию (не
    автоматически с первым сообщением, см. риск-баннер на вкладке
    Telegram про то, почему)."""
    creds = _telegram_secrets(ctx)
    if creds is None:
        raise HTTPException(
            400, "Сначала вставьте api_id и api_hash: Общение → Telegram-парсер → «Подключение аккаунта»."
        )
    resume_path = ctx.config["dataFolder"] / RESUME_PDF
    if not resume_path.exists():
        raise HTTPException(400, f"{RESUME_PDF} not found in data_folder")
    try:
        with TelegramSourceClient(
            int(creds[0]), creds[1], _telegram_session_path(ctx)
        ) as client:
            client.send_file(contact, resume_path)
    except Exception as e:
        raise HTTPException(502, f"Failed to send resume: {e}")

    conversations = TelegramConversations(
        ctx.output_folder / "telegram_conversations.json"
    )
    conversations.record_outbound(
        contact, f"📎 Отправлено резюме ({RESUME_PDF})"
    )
    conv = conversations.get(contact)
    if conv is None:
        raise HTTPException(500, "Conversation vanished after send")
    return conv


@app.delete("/api/telegram/conversations/{contact}")
def delete_telegram_conversation(
    contact: str, ctx: AppContext = Depends(get_ctx)
) -> dict:
    conversations = TelegramConversations(
        ctx.output_folder / "telegram_conversations.json"
    )
    existed = conversations.delete(contact)
    if not existed:
        raise HTTPException(404, f"No conversation with @{contact}")
    return {"deleted": contact}


@app.post("/api/settings/generate-positions")
def post_generate_positions(ctx: AppContext = Depends(get_ctx)) -> dict:
    """Кнопка "Сгенерировать из резюме" — один LLM-вызов (не Selenium),
    как /api/resume/refresh-plain-text, поэтому тоже синхронно, без
    фонового потока. Сразу сохраняет результат в positions: — та же
    логика, что автовывод positions на старте CLI при пустом
    work_preferences.yaml (main.generate_positions_from_resume)."""
    try:
        positions = _generate_positions(ctx.config, ctx.llm_api_key)
    except FileNotFoundError as e:
        raise HTTPException(400, str(e))
    set_list_field(ctx.config_file, "positions", positions)
    ctx.reload_config()
    return {"positions": positions}


_JOB_APPLICATION_PROFILE_YAML = "job_application_profile.yaml"


class SalarySettingsUpdate(BaseModel):
    hh_salary_expectations: Optional[str] = None
    linkedin_salary_range_usd: Optional[str] = None


def _profile_file(ctx: AppContext) -> Path:
    return ctx.config["dataFolder"] / _JOB_APPLICATION_PROFILE_YAML


def _salary_snapshot(ctx: AppContext) -> dict:
    profile_file = _profile_file(ctx)
    profile = (
        (ConfigValidator.load_yaml(profile_file) or {})
        if profile_file.exists()
        else {}
    )
    return {
        # HH: подсказка для LLM в автоответе чата (reply_answerer.py),
        # рубли/месяц — российский рынок.
        "hh_salary_expectations": ctx.config.get("salary_expectations") or "",
        # LinkedIn: ответ на скрининговые вопросы Easy Apply,
        # доллары/год — международный рынок, намеренно отдельное поле
        # (см. комментарий в job_application_profile.yaml).
        "linkedin_salary_range_usd": (
            profile.get("salary_expectations") or {}
        ).get("salary_range_usd")
        or "",
    }


@app.get("/api/settings/salary")
def get_salary_settings(ctx: AppContext = Depends(get_ctx)) -> dict:
    return _salary_snapshot(ctx)


@app.post("/api/settings/salary")
def post_salary_settings(
    body: SalarySettingsUpdate, ctx: AppContext = Depends(get_ctx)
) -> dict:
    if body.hh_salary_expectations is not None:
        set_top_level_field(
            ctx.config_file, "salary_expectations", body.hh_salary_expectations
        )
        ctx.reload_config()
    if body.linkedin_salary_range_usd is not None:
        profile_file = _profile_file(ctx)
        if not profile_file.exists():
            raise HTTPException(
                400,
                f"{_JOB_APPLICATION_PROFILE_YAML} not found: {profile_file}",
            )
        set_source_field(
            profile_file,
            "salary_expectations",
            "salary_range_usd",
            body.linkedin_salary_range_usd,
            quote=True,
        )
    return _salary_snapshot(ctx)


_KNOWN_LLM_PROVIDERS = {
    "openai",
    "groq",
    "gemini",
    "deepseek",
    "nvidia",
    "openrouter",
    "mistral",
    "cohere",
    "huggingface",
    "ollama_cloud",
    "llm7",
    "cloudflare",
    "vercel",
    "ollama",
}


def _mask_api_key(key: str) -> str:
    if len(key) <= 8:
        return "•" * len(key)
    return f"{key[:4]}…{key[-4:]}"


def _llm_snapshot(ctx: AppContext) -> dict:
    llm_config = ctx.config.get("llm") or {}
    provider = llm_config.get("provider") or LLM_MODEL_TYPE
    # Дефолты из config.py (LLM_MODEL/LLM_API_URL) относятся к
    # LLM_MODEL_TYPE — показывать их для другого провайдера вводило
    # бы в заблуждение (например "gpt-4o-mini" рядом с активным
    # Groq, хотя реально используется openai/gpt-oss-120b).
    is_config_default = provider == LLM_MODEL_TYPE
    secrets = ConfigValidator.load_yaml(ctx.secrets_file)
    stored_keys = secrets.get("llm_api_keys") or {}
    key_previews = {
        p: _mask_api_key(stored_keys[p])
        for p in _KNOWN_LLM_PROVIDERS
        if stored_keys.get(p)
    }
    # Легаси-ключ всегда относится к LLM_MODEL_TYPE (тому единственному
    # провайдеру, для которого он заводился раньше) — вне зависимости
    # от того, какой провайдер сейчас активен, чтобы карточка openai
    # в UI показывала свой ключ, даже когда выбран, например, groq.
    legacy_key = secrets.get("llm_api_key")
    if legacy_key and LLM_MODEL_TYPE not in key_previews:
        key_previews[LLM_MODEL_TYPE] = _mask_api_key(legacy_key)
    # Не секрет как ключ (это адрес, не пароль) — показывается в
    # дашборде как есть, без маскировки.
    provider_base_urls = secrets.get("llm_provider_base_urls") or {}
    return {
        "provider": provider,
        "model": llm_config.get("model")
        or (LLM_MODEL if is_config_default else None),
        "base_url": llm_config.get("base_url")
        or (LLM_API_URL or None if is_config_default else None),
        "models": PROVIDER_MODELS,
        "api_key_previews": key_previews,
        "provider_base_urls": provider_base_urls,
        "mode": llm_config.get("mode") or "auto",
        "fallback_enabled": llm_config.get("fallback_enabled", True),
    }


@app.get("/api/settings/llm")
def get_llm_settings(ctx: AppContext = Depends(get_ctx)) -> dict:
    return _llm_snapshot(ctx)


_KNOWN_LLM_MODES = {"free", "paid", "auto"}


class LLMProviderUpdate(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None
    base_url: Optional[str] = None
    mode: Optional[str] = None
    fallback_enabled: Optional[bool] = None


@app.post("/api/settings/llm")
def post_llm_settings(
    body: LLMProviderUpdate, ctx: AppContext = Depends(get_ctx)
) -> dict:
    """llm: — тот же плоский top-level блок в work_preferences.yaml,
    что limits:/headhunter:, применяется сразу через
    apply_llm_provider_override() внутри ctx.reload_config() — без
    перезапуска процесса."""
    if body.provider is not None:
        if body.provider not in _KNOWN_LLM_PROVIDERS:
            raise HTTPException(400, f"Unknown provider: {body.provider}")
        set_source_field(ctx.config_file, "llm", "provider", body.provider)
    if body.model is not None:
        set_source_field(ctx.config_file, "llm", "model", body.model)
    if body.mode is not None:
        if body.mode not in _KNOWN_LLM_MODES:
            raise HTTPException(400, f"Unknown mode: {body.mode}")
        set_source_field(ctx.config_file, "llm", "mode", body.mode)
    if body.fallback_enabled is not None:
        set_source_field(
            ctx.config_file, "llm", "fallback_enabled", body.fallback_enabled
        )
    if body.base_url is not None:
        set_source_field(ctx.config_file, "llm", "base_url", body.base_url)
    ctx.reload_config()
    return _llm_snapshot(ctx)


class LLMKeyUpdate(BaseModel):
    provider: str
    api_key: str


@app.post("/api/settings/llm-key")
def post_llm_key(
    body: LLMKeyUpdate, ctx: AppContext = Depends(get_ctx)
) -> dict:
    """Пишет ключ в llm_api_keys.<provider> — не в общий legacy
    llm_api_key — чтобы ключи разных провайдеров не перезаписывали
    друг друга (у каждого свой: OpenAI/Groq/Gemini/DeepSeek/...)."""
    if body.provider not in _KNOWN_LLM_PROVIDERS:
        raise HTTPException(400, f"Unknown provider: {body.provider}")
    key = body.api_key.strip()
    if not key:
        raise HTTPException(400, "api_key must not be empty")
    set_source_field(
        ctx.secrets_file, "llm_api_keys", body.provider, key, quote=True
    )
    if _active_llm() == body.provider:
        ctx.llm_api_key = key
    return {"provider": body.provider, "api_key_preview": _mask_api_key(key)}


class LLMProviderBaseUrlUpdate(BaseModel):
    provider: str
    base_url: str


@app.post("/api/settings/llm-provider-base-url")
def post_llm_provider_base_url(
    body: LLMProviderBaseUrlUpdate, ctx: AppContext = Depends(get_ctx)
) -> dict:
    """Пишет llm_provider_base_urls.<provider> — только для
    провайдеров без единого статического эндпоинта (сейчас — только
    Cloudflare Workers AI, у которого account_id зашит в URL). Тот же
    приём, что post_llm_key(), но для второго секрета вместо ключа."""
    if body.provider not in _KNOWN_LLM_PROVIDERS:
        raise HTTPException(400, f"Unknown provider: {body.provider}")
    url = body.base_url.strip()
    if not url:
        raise HTTPException(400, "base_url must not be empty")
    set_source_field(
        ctx.secrets_file,
        "llm_provider_base_urls",
        body.provider,
        url,
        quote=True,
    )
    ctx.reload_config()
    return {"provider": body.provider, "base_url": url}


@app.get("/api/logs")
def get_logs(lines: int = 200, source: Optional[str] = None) -> dict:
    if not LOG_TO_FILE or not LOG_FILE.exists():
        return {
            "lines": [],
            "note": (
                "File logging is disabled (config.LOG_TO_FILE = False) "
                "or log/app.log does not exist yet."
            ),
        }
    tail = LOG_FILE.read_text(encoding="utf-8").splitlines()[-lines:]
    if source:
        tail = [line for line in tail if source.lower() in line.lower()]
    return {"lines": tail, "note": None}


@app.post("/api/daemon/start")
def start_daemon(ctx: AppContext = Depends(get_ctx)) -> dict:
    if ctx.scheduler_thread is not None and ctx.scheduler_thread.is_alive():
        return {"running": True}
    stop_event = threading.Event()
    ctx.scheduler = Scheduler(
        SCHEDULER_SOURCES,
        ctx.config,
        ctx.llm_api_key,
        ctx.output_folder,
        stop_event=stop_event,
    )
    ctx.scheduler_thread = threading.Thread(
        target=ctx.scheduler.run_forever, daemon=True
    )
    ctx.scheduler_thread.start()
    ctx.daemon_started_at = datetime.now(timezone.utc).isoformat()
    return {"running": True}


@app.post("/api/daemon/stop")
def stop_daemon(ctx: AppContext = Depends(get_ctx)) -> dict:
    if ctx.scheduler is not None:
        ctx.scheduler.stop()
    if ctx.scheduler_thread is not None:
        ctx.scheduler_thread.join(timeout=5)
    ctx.scheduler = None
    ctx.scheduler_thread = None
    ctx.daemon_started_at = None
    return {"running": False}


@app.post("/api/daemon/pause")
def pause_daemon(ctx: AppContext = Depends(get_ctx)) -> dict:
    """Пауза = планировщик продолжает тикать (run_forever жив), но
    due_sources() перестаёт отдавать источники — уже идущий ручной
    запуск (run-now) это не трогает, только новые плановые запуски."""
    if ctx.scheduler is None:
        raise HTTPException(409, "Daemon is not running.")
    ctx.scheduler.paused = True
    return {"paused": True}


@app.post("/api/daemon/resume")
def resume_daemon(ctx: AppContext = Depends(get_ctx)) -> dict:
    if ctx.scheduler is None:
        raise HTTPException(409, "Daemon is not running.")
    ctx.scheduler.paused = False
    return {"paused": False}


class RunNowRequest(BaseModel):
    sources: list[str]
    # Дашборд — кнопка "Тестовый прогон": форсирует dry-run для всех
    # выбранных площадок независимо от их auto_apply/auto_message в
    # work_preferences.yaml, ничего в самом файле не меняя (см.
    # run_selected_sources в main.py).
    dry_run: bool = False


@app.post("/api/run-now")
def post_run_now(
    body: RunNowRequest, ctx: AppContext = Depends(get_ctx)
) -> dict:
    """Мультивыбор источников, как уже есть в CLI (меню "Search
    selected sources") — запускает выбранные источники один раз,
    сейчас, а не по расписанию демона. Переиспользует
    run_selected_sources() из main.py как есть."""
    if ctx.run_now_thread is not None and ctx.run_now_thread.is_alive():
        raise HTTPException(409, "A manual run is already in progress.")
    if not body.sources:
        raise HTTPException(400, "No sources selected.")
    unknown = [s for s in body.sources if s not in dict(ALL_SOURCES)]
    if unknown:
        raise HTTPException(400, f"Unknown source(s): {', '.join(unknown)}")

    stop_event = threading.Event()

    def _run() -> None:
        try:
            run_selected_sources(
                body.sources,
                ctx.config,
                ctx.llm_api_key,
                dry_run=body.dry_run,
                on_source_start=lambda name: setattr(
                    ctx, "run_now_current_source", name
                ),
                stop_event=stop_event,
            )
        finally:
            ctx.run_now_sources = []
            ctx.run_now_current_source = None
            ctx.run_now_stop_event = None

    ctx.run_now_sources = body.sources
    ctx.run_now_dry_run = body.dry_run
    ctx.run_now_stop_event = stop_event
    ctx.run_now_thread = threading.Thread(target=_run, daemon=True)
    ctx.run_now_thread.start()
    return {"started": True, "sources": body.sources, "dry_run": body.dry_run}


@app.post("/api/run-now/stop")
def post_run_now_stop(ctx: AppContext = Depends(get_ctx)) -> dict:
    """Мягкий стоп: помечает stop_event, который search_and_apply_*
    проверяет между вакансиями (main.py), а run_selected_sources — между
    источниками. Текущая уже начатая заявка досылается, следующая не
    начинается — жёсткого прерывания посреди клика "Откликнуться" нет,
    чтобы не оставлять форму в неопределённом состоянии на площадке."""
    running = ctx.run_now_thread is not None and ctx.run_now_thread.is_alive()
    if running and ctx.run_now_stop_event is not None:
        ctx.run_now_stop_event.set()
    return {"stopping": running}


@app.get("/api/run-now/status")
def get_run_now_status(ctx: AppContext = Depends(get_ctx)) -> dict:
    running = ctx.run_now_thread is not None and ctx.run_now_thread.is_alive()
    stopping = running and bool(
        ctx.run_now_stop_event is not None and ctx.run_now_stop_event.is_set()
    )
    return {
        "running": running,
        "sources": ctx.run_now_sources if running else [],
        "dry_run": ctx.run_now_dry_run if running else False,
        "current_source": ctx.run_now_current_source if running else None,
        "stopping": stopping,
    }


@app.post("/api/notifications/test")
def post_test_notification(ctx: AppContext = Depends(get_ctx)) -> dict:
    """В отличие от main.notify() (best-effort, глотает ошибки) — эта
    ручка нужна, чтобы пользователь сразу узнал, настроен ли бот
    правильно, а не по факту первого реального события."""
    secrets = ConfigValidator.load_yaml(ctx.secrets_file)
    notifications = secrets.get("notifications") or {}
    bot_token = notifications.get("telegram_bot_token")
    chat_id = notifications.get("telegram_chat_id")
    if not bot_token or not chat_id:
        raise HTTPException(
            400,
            "Бот уведомлений не подключён — Настройки → «Уведомления (бот)».",
        )
    try:
        send_notification(
            bot_token, chat_id, "CrossJob-AI: тестовое уведомление."
        )
    except Exception as e:
        raise HTTPException(502, f"Не удалось отправить: {e}")
    return {"sent": True}


class TelegramTokenUpdate(BaseModel):
    bot_token: str


@app.post("/api/settings/telegram/token")
def post_telegram_token(
    body: TelegramTokenUpdate, ctx: AppContext = Depends(get_ctx)
) -> dict:
    """Сохраняет только bot_token и проверяет его через getMe — chat_id
    достаётся отдельным шагом (POST .../connect), автоматически, без
    похода в браузер за getUpdates вручную."""
    token = body.bot_token.strip()
    if not token:
        raise HTTPException(400, "bot_token must not be empty")
    try:
        username = get_bot_username(token)
    except Exception as e:
        raise HTTPException(400, f"Неверный токен бота: {e}")
    set_source_field(
        ctx.secrets_file,
        "notifications",
        "telegram_bot_token",
        token,
        quote=True,
    )
    return {
        "username": username,
        "connect_url": f"https://t.me/{username}?start=connect",
    }


@app.post("/api/settings/telegram/connect")
def post_telegram_connect(ctx: AppContext = Depends(get_ctx)) -> dict:
    """Запускает фоновый поллинг getUpdates в ожидании /start от
    пользователя (см. wait_for_start) — пишет chat_id и шлёт
    приветствие сам, без ручного копипаста id из JSON."""
    secrets = ConfigValidator.load_yaml(ctx.secrets_file)
    bot_token = (secrets.get("notifications") or {}).get("telegram_bot_token")
    if not bot_token:
        raise HTTPException(400, "Сначала сохраните bot_token.")
    if (
        ctx.telegram_connect_thread is not None
        and ctx.telegram_connect_thread.is_alive()
    ):
        return ctx.telegram_connect_status

    ctx.telegram_connect_status = {"status": "waiting"}

    def _poll() -> None:
        chat_id = wait_for_start(bot_token, timeout_seconds=180)
        if chat_id is None:
            ctx.telegram_connect_status = {"status": "timeout"}
            return
        set_source_field(
            ctx.secrets_file,
            "notifications",
            "telegram_chat_id",
            chat_id,
            quote=True,
        )
        try:
            send_notification(
                bot_token,
                chat_id,
                "✅ CrossJob-AI подключён! Сюда будут приходить уведомления "
                "о статусе площадок, лимитах и подтверждения нестандартных "
                "анкет.\n\n" + _TELEGRAM_HELP_TEXT,
            )
        except Exception:
            pass
        ctx.telegram_connect_status = {
            "status": "connected",
            "chat_id": chat_id,
        }

    ctx.telegram_connect_thread = threading.Thread(target=_poll, daemon=True)
    ctx.telegram_connect_thread.start()
    return ctx.telegram_connect_status


@app.get("/api/settings/telegram/connect/status")
def get_telegram_connect_status(ctx: AppContext = Depends(get_ctx)) -> dict:
    # idle (свежий процесс, ещё не запускали /connect в этом сеансе)
    # не значит "не подключено" — secrets.yaml мог быть настроен в
    # прошлом запуске приложения; проверяем файл, чтобы UI сразу
    # показал "подключено", а не заставлял проходить шаги заново.
    if ctx.telegram_connect_status.get("status") == "idle":
        secrets = ConfigValidator.load_yaml(ctx.secrets_file)
        notifications = secrets.get("notifications") or {}
        chat_id = notifications.get("telegram_chat_id")
        if notifications.get("telegram_bot_token") and chat_id:
            return {"status": "connected", "chat_id": chat_id}
    return ctx.telegram_connect_status


@app.post("/api/resume/refresh-plain-text")
def post_refresh_plain_text_resume(
    ctx: AppContext = Depends(get_ctx),
) -> dict:
    """plain_text_resume.yaml генерируется из resume.pdf один раз и
    дальше переиспользуется (ensure_plain_text_resume) — если
    пользователь заменил resume.pdf, кэш иначе остаётся старым.
    Один LLM-вызов (не Selenium) — достаточно быстрый, чтобы не
    заводить фоновый поток/поллинг, как у /api/generate/*."""
    try:
        path = _refresh_plain_text(ctx.config, ctx.llm_api_key)
    except FileNotFoundError as e:
        raise HTTPException(400, str(e))
    return {"refreshed": True, "path": str(path)}


@app.get("/api/generate/styles")
def get_generate_styles() -> list[str]:
    return list(StyleManager().get_styles().keys())


@app.get("/api/generate/styles/ats-report")
def get_generate_styles_ats_report() -> dict[str, list[str]]:
    """Риски ATS по каждому стилю (пустой список — риск не найден),
    см. StyleManager.get_ats_report()/analyze_ats_risks — статическая
    проверка CSS-шаблона, не требует реальной генерации PDF."""
    return StyleManager().get_ats_report()


class GenerateRequest(BaseModel):
    style_name: Optional[str] = None
    job_url: Optional[str] = None


_GENERATORS = {
    "resume": lambda ctx, body: _create_resume_pdf(
        ctx.config, ctx.llm_api_key, style_name=body.style_name
    ),
    "resume-tailored": lambda ctx, body: _create_resume_tailored(
        ctx.config,
        ctx.llm_api_key,
        style_name=body.style_name,
        job_url=body.job_url,
    ),
    "cover-letter": lambda ctx, body: _create_cover_letter(
        ctx.config,
        ctx.llm_api_key,
        style_name=body.style_name,
        job_url=body.job_url,
    ),
    "resume-audit": lambda ctx, body: _create_resume_audit(
        ctx.config,
        ctx.llm_api_key,
        job_url=body.job_url,
    ),
}
# resume-audit возвращает dict (текст 3 шагов аудита), а не путь к PDF —
# единственный генератор, для которого /api/generate/download не имеет
# смысла; сам /api/generate/{kind}+status ниже это отличие не знает,
# просто кладёт "result" вместо "path" в ctx.generate_result.
_TEXT_RESULT_GENERATORS = {"resume-audit"}


@app.post("/api/generate/{kind}")
def post_generate(
    kind: str, body: GenerateRequest, ctx: AppContext = Depends(get_ctx)
) -> dict:
    """Резюме/сопроводительное под конкретную вакансию — тот же
    ResumeFacade+Selenium, что и в консольном меню (Generate Resume /
    Generate Resume Tailored / Generate Tailored Cover Letter), но
    вызывается с явными style_name/job_url вместо inquirer-промптов,
    т.к. дашборд не может отвечать на вопросы в терминале. Рендер PDF
    через Selenium небыстрый — гоняем в фоновом потоке, как run-now."""
    if kind not in _GENERATORS:
        raise HTTPException(404, f"Unknown generator: {kind}")
    if (
        kind in ("resume-tailored", "cover-letter", "resume-audit")
        and not body.job_url
    ):
        raise HTTPException(400, "job_url is required for this generator.")
    if ctx.generate_thread is not None and ctx.generate_thread.is_alive():
        raise HTTPException(409, "A generation is already in progress.")

    def _run() -> None:
        try:
            output = _GENERATORS[kind](ctx, body)
            if kind in _TEXT_RESULT_GENERATORS:
                ctx.generate_result = {"ready": True, "result": output}
            else:
                ctx.generate_result = {"ready": True, "path": str(output)}
        except Exception as e:
            ctx.generate_result = {"ready": True, "error": str(e)}

    ctx.generate_result = {}
    ctx.generate_thread = threading.Thread(target=_run, daemon=True)
    ctx.generate_thread.start()
    return {"started": True, "kind": kind}


@app.get("/api/generate/status")
def get_generate_status(ctx: AppContext = Depends(get_ctx)) -> dict:
    running = (
        ctx.generate_thread is not None and ctx.generate_thread.is_alive()
    )
    return {"running": running, **ctx.generate_result}


@app.get("/api/generate/download")
def get_generate_download(ctx: AppContext = Depends(get_ctx)) -> FileResponse:
    path = ctx.generate_result.get("path")
    if not path or not Path(path).exists():
        raise HTTPException(404, "No generated file available.")
    return FileResponse(path, filename=Path(path).name)


# kind="primary" — HeadHunter/geekjob/GetMatch/Хабр Карьера/Telegram
# (RESUME_PDF). kind="linkedin" — LinkedIn/Wellfound/Himalayas,
# опционально (RESUME_PDF_LINKEDIN, см. main.py) — без него эти три
# площадки сами откатываются на resume.pdf.
_RESUME_UPLOAD_FILENAME = {
    "primary": RESUME_PDF,
    "linkedin": RESUME_PDF_LINKEDIN,
}


@app.post("/api/resume/upload")
async def post_resume_upload(
    kind: str,
    file: UploadFile = File(...),
    ctx: AppContext = Depends(get_ctx),
) -> dict:
    """Кнопка загрузки резюме в дашборде — заменяет ручное копирование
    PDF в data_folder через Finder/Проводник."""
    filename = _RESUME_UPLOAD_FILENAME.get(kind)
    if filename is None:
        raise HTTPException(400, "kind must be 'primary' or 'linkedin'")
    content = await file.read()
    if not content.startswith(b"%PDF-"):
        raise HTTPException(400, "Файл не похож на PDF.")
    (ctx.config["dataFolder"] / filename).write_bytes(content)
    return {"filename": filename, "size": len(content)}


if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
