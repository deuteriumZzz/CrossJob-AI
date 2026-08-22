from __future__ import annotations

import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import (
    DAILY_APPLICATION_LIMIT,
    JOB_MAX_APPLICATIONS,
    LINKEDIN_DAILY_APPLICATION_LIMIT,
    LLM_API_URL,
    LLM_MODEL,
    LLM_MODEL_TYPE,
    LOG_TO_FILE,
)
from main import ALL_SOURCES, ConfigError, ConfigValidator, FileManager
from main import _daily_limit as _effective_daily_limit
from main import _job_max_applications as _effective_job_max_applications
from main import append_to_company_blacklist as _append_to_blacklist
from main import apply_llm_provider_override
from main import bootstrap_data_folder as _bootstrap_data_folder
from main import create_cover_letter as _create_cover_letter
from main import create_resume_pdf as _create_resume_pdf
from main import create_resume_pdf_job_tailored as _create_resume_tailored
from main import force_refresh_plain_text_resume as _refresh_plain_text
from main import generate_positions_from_resume as _generate_positions
from main import run_selected_sources
from src.config_patch import (
    set_list_field,
    set_source_field,
    set_source_list_field,
)
from src.job_sources.applied_log import AppliedLog
from src.job_sources.llm_provider import PROVIDER_MODELS
from src.job_sources.llm_provider import get_active_provider as _active_llm
from src.job_sources.llm_usage import (
    set_output_folder as set_llm_usage_output_folder,
)
from src.job_sources.llm_usage import (
    summarize_usage,
)
from src.job_sources.telegram_notify import send_notification
from src.libs.resume_and_cover_builder import StyleManager
from src.scheduler import Scheduler
from src.scheduler_state import load_state
from src.utils.constants import SECRETS_YAML

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
        self.llm_api_key = self._resolve_llm_api_key()
        self.applied_log = AppliedLog(self.output_folder / "applied_log.json")
        self.scheduler: Optional[Scheduler] = None
        self.scheduler_thread: Optional[threading.Thread] = None
        self.run_now_thread: Optional[threading.Thread] = None
        self.run_now_sources: list[str] = []
        self.generate_thread: Optional[threading.Thread] = None
        self.generate_result: dict = {}

    def reload_config(self) -> None:
        fresh = ConfigValidator.validate_config(self.config_file)
        self.config.update(fresh)
        apply_llm_provider_override(self.config)
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
# None — источнику вообще не нужны секреты (скрейпинг без аккаунта).
_CREDENTIAL_REQUIREMENTS: dict = {
    "headhunter": ("client_id", "client_secret"),
    "superjob": ("client_id", "client_secret"),
    "zarplata": ("client_id", "client_secret"),
    "geekjob": None,
    "rabota_ru": None,
    "telegram": ("api_id", "api_hash"),
    "getmatch": ("email",),
    "linkedin": ("email", "password"),
}


def _readiness(secrets: dict, source: str) -> dict:
    required = _CREDENTIAL_REQUIREMENTS.get(source)
    if required is None:
        return {"ready": True, "missing": []}
    block = secrets.get(source) or {}
    missing = [field for field in required if not block.get(field)]
    return {"ready": not missing, "missing": missing}


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
                "resume_id": source_config.get("resume_id") or "",
                "interval_hours": source_config.get("interval_hours"),
                "last_run": entry.get("last_run"),
                "next_run": entry.get("next_run"),
                "status": entry.get("status", "never_run"),
                "last_error": entry.get("last_error"),
                "applied_today": ctx.applied_log.applied_today_count(name),
                "daily_limit": _effective_daily_limit(ctx.config, name),
                "job_max_applications": _effective_job_max_applications(
                    ctx.config, name
                ),
                "readiness": _readiness(secrets, name),
            }
        )
    return {
        "daemon_running": ctx.scheduler_thread is not None
        and ctx.scheduler_thread.is_alive(),
        "sources": sources,
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
    return summarize_usage(ctx.output_folder)


@app.get("/api/analytics/gaps")
def get_gaps(ctx: AppContext = Depends(get_ctx)) -> list[list]:
    return [list(item) for item in ctx.applied_log.most_common_gaps()]


@app.get("/api/analytics/blacklist-candidates")
def get_blacklist_candidates(
    ctx: AppContext = Depends(get_ctx),
) -> list[str]:
    return ctx.applied_log.suggest_blacklist_candidates()


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
    schedule_enabled: Optional[bool] = None
    interval_hours: Optional[int] = None
    resume_id: Optional[str] = None
    job_max_applications: Optional[int] = None
    daily_application_limit: Optional[int] = None


@app.post("/api/settings")
def post_settings(
    body: SourceSettingsUpdate, ctx: AppContext = Depends(get_ctx)
) -> dict:
    if body.source not in dict(ALL_SOURCES):
        raise HTTPException(400, f"Unknown source: {body.source}")
    for field in (
        "auto_apply",
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
        # самой площадке (hh.ru/superjob.ru/zarplata.ru) — бот его не
        # создаёт и не перезаписывает, только передаёт при отклике.
        # quote=True: id может содержать произвольные символы.
        set_source_field(
            ctx.config_file,
            body.source,
            "resume_id",
            body.resume_id,
            quote=True,
        )
    ctx.reload_config()
    return {"source": body.source, "updated": True}


class LimitsSettingsUpdate(BaseModel):
    daily_application_limit: Optional[int] = None
    linkedin_daily_application_limit: Optional[int] = None
    job_max_applications: Optional[int] = None
    llm_daily_cost_alert_usd: Optional[float] = None


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
        "job_max_applications": limits.get(
            "job_max_applications", JOB_MAX_APPLICATIONS
        ),
        "llm_daily_cost_alert_usd": limits.get("llm_daily_cost_alert_usd"),
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
    ctx.reload_config()
    return _limits_snapshot(ctx)


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
    telegram_channels: Optional[list[str]] = None


def _search_snapshot(ctx: AppContext) -> dict:
    snapshot = {
        field: ctx.config.get(field) or [] for field in _SEARCH_LIST_FIELDS
    }
    snapshot["telegram_channels"] = (ctx.config.get("telegram") or {}).get(
        "channels"
    ) or []
    return snapshot


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
    if body.telegram_channels is not None:
        set_source_list_field(
            ctx.config_file, "telegram", "channels", body.telegram_channels
        )
    ctx.reload_config()
    return _search_snapshot(ctx)


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


_KNOWN_LLM_PROVIDERS = {"openai", "groq", "gemini", "deepseek", "ollama"}


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
    return {
        "provider": provider,
        "model": llm_config.get("model")
        or (LLM_MODEL if is_config_default else None),
        "base_url": llm_config.get("base_url")
        or (LLM_API_URL or None if is_config_default else None),
        "models": PROVIDER_MODELS,
        "api_key_previews": key_previews,
    }


@app.get("/api/settings/llm")
def get_llm_settings(ctx: AppContext = Depends(get_ctx)) -> dict:
    return _llm_snapshot(ctx)


class LLMProviderUpdate(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None
    base_url: Optional[str] = None


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
        dict(ALL_SOURCES),
        ctx.config,
        ctx.llm_api_key,
        ctx.output_folder,
        stop_event=stop_event,
    )
    ctx.scheduler_thread = threading.Thread(
        target=ctx.scheduler.run_forever, daemon=True
    )
    ctx.scheduler_thread.start()
    return {"running": True}


@app.post("/api/daemon/stop")
def stop_daemon(ctx: AppContext = Depends(get_ctx)) -> dict:
    if ctx.scheduler is not None:
        ctx.scheduler.stop()
    if ctx.scheduler_thread is not None:
        ctx.scheduler_thread.join(timeout=5)
    ctx.scheduler = None
    ctx.scheduler_thread = None
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
