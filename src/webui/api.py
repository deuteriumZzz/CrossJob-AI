from __future__ import annotations

import random
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import (
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
from main import bootstrap_data_folder as _bootstrap_data_folder
from main import (
    clone_headhunter_resume,
)
from main import create_cover_letter as _create_cover_letter
from main import (
    create_headhunter_resume_draft,
)
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
)
from src.job_sources.applied_log import AppliedLog
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
from src.job_sources.telegram_conversations import TelegramConversations
from src.job_sources.telegram_notify import send_notification
from src.libs.resume_and_cover_builder import StyleManager
from src.logging import logger
from src.scheduler import DEFAULT_INTERVAL_HOURS, Scheduler
from src.scheduler_state import load_state
from src.utils import autostart
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


_data_folder = Path("data_folder")
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
    "superjob": ("client_id", "client_secret"),
    "geekjob": None,
    "rabota_ru": None,
    "telegram": ("api_id", "api_hash"),
    "getmatch": ("email",),
    "linkedin": None,
    "habr_career": None,
}


# Площадки, где резюме уже есть прямо в личном кабинете (getmatch,
# rabota_ru и т.д.) не требуют локального PDF для отклика — только
# HeadHunter и LinkedIn реально читают файл из data_folder перед
# откликом (см. RESUME_PDF/RESUME_PDF_LINKEDIN в main.py). Заявлять
# "резюме не найдено" для остальных площадок было бы ложной тревогой.
_RESUME_FILENAME_BY_SOURCE = {
    "headhunter": RESUME_PDF,
    "linkedin": RESUME_PDF_LINKEDIN,
}


def _resume_readiness(data_folder: Path, source: str) -> Optional[dict]:
    filename = _RESUME_FILENAME_BY_SOURCE.get(source)
    if filename is None:
        return None
    if (data_folder / filename).exists():
        return {"ready": True, "filename": filename}
    # LinkedIn молча падает назад на resume.pdf (см.
    # search_and_apply_linkedin в main.py) — не ложная тревога, если
    # общий файл всё же есть, просто предупреждаем про язык/локацию.
    if source == "linkedin" and (data_folder / RESUME_PDF).exists():
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
        ("rate_limit_exceeded", "rate limit"),
        "Провайдер LLM временно перегружен — бот подождёт и повторит "
        "на следующем прогоне.",
    ),
    (
        ("invalid_api_key", "incorrect api key", "401"),
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
            "label": "HeadHunter — ответы в чате",
            "note": "Работает только если включён headhunter.auto_reply.",
        },
        {
            "name": "check_sj_replies",
            "label": "SuperJob — статус откликов",
            "note": "Только уведомление, без автоответа.",
        },
        {
            "name": "check_telegram_replies",
            "label": "Telegram — новые сообщения в диалогах",
            "note": (
                "Только уведомление — отвечать нужно вручную "
                "во вкладке Telegram."
            ),
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
    return entries


@app.get("/api/replies")
def get_replies(ctx: AppContext = Depends(get_ctx)) -> list[dict]:
    entries = [
        e
        for e in ctx.applied_log.find_by_company("")
        if e.get("last_known_state")
    ]
    return sorted(entries, key=lambda e: e["applied_at"], reverse=True)


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
        "job_max_applications",
        "daily_application_limit",
    ):
        value = getattr(body, field)
        if value is not None:
            if (
                field
                in (
                    "job_max_applications",
                    "daily_application_limit",
                )
                and value < 1
            ):
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
    """Раскидывает total между sources случайными долями (LinkedIn —
    вдвое меньший вес по умолчанию, см. risk-banner в дашборде: банит
    автоматизацию агрессивнее остальных площадок). Сумма долей после
    округления вниз почти всегда меньше total — остаток раздаётся по
    одной штуке в случайном порядке, чтобы сумма сошлась ровно."""
    weights = {
        s: (0.5 if s == "linkedin" else 1.0) * random.uniform(0.6, 1.4)
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
    creds = _telegram_secrets(ctx)
    if creds is None:
        return {"configured": False, "connected": False}
    try:
        with TelegramStatusClient(
            int(creds[0]), creds[1], _telegram_session_path(ctx)
        ) as client:
            connected = client.is_authorized()
    except Exception as e:
        logger.warning(f"Failed to check Telegram session status: {e}")
        return {"configured": True, "connected": False}
    return {"configured": True, "connected": connected}


class TelegramLoginPhone(BaseModel):
    phone: str


class TelegramLoginCode(BaseModel):
    code: str


class TelegramLoginPassword(BaseModel):
    password: str


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
            400, "telegram.api_id/api_hash не заданы в secrets.yaml."
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
            400, "Missing telegram.api_id/api_hash in secrets.yaml"
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
            400, "Missing telegram.api_id/api_hash in secrets.yaml"
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


class RunNowRequest(BaseModel):
    sources: list[str]


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

    def _run() -> None:
        try:
            run_selected_sources(body.sources, ctx.config, ctx.llm_api_key)
        finally:
            ctx.run_now_sources = []

    ctx.run_now_sources = body.sources
    ctx.run_now_thread = threading.Thread(target=_run, daemon=True)
    ctx.run_now_thread.start()
    return {"started": True, "sources": body.sources}


@app.get("/api/run-now/status")
def get_run_now_status(ctx: AppContext = Depends(get_ctx)) -> dict:
    running = ctx.run_now_thread is not None and ctx.run_now_thread.is_alive()
    return {
        "running": running,
        "sources": ctx.run_now_sources if running else [],
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
            "notifications.telegram_bot_token/telegram_chat_id не "
            "заданы в secrets.yaml.",
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
}


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
    if kind in ("resume-tailored", "cover-letter") and not body.job_url:
        raise HTTPException(400, "job_url is required for this generator.")
    if ctx.generate_thread is not None and ctx.generate_thread.is_alive():
        raise HTTPException(409, "A generation is already in progress.")

    def _run() -> None:
        try:
            path = _GENERATORS[kind](ctx, body)
            ctx.generate_result = {"ready": True, "path": str(path)}
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


if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
