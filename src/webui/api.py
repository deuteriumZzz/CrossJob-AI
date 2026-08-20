from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import DAILY_APPLICATION_LIMIT, LOG_TO_FILE
from main import ALL_SOURCES, ConfigValidator, FileManager
from main import append_to_company_blacklist as _append_to_blacklist
from main import run_selected_sources
from src.config_patch import set_source_field
from src.job_sources.applied_log import AppliedLog
from src.job_sources.telegram_notify import send_notification
from src.scheduler import Scheduler
from src.scheduler_state import load_state

STATIC_DIR = Path(__file__).parent / "static"
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
        self.llm_api_key = ConfigValidator.validate_secrets(self.secrets_file)
        self.config["outputFileDirectory"] = self.output_folder
        self.config["dataFolder"] = data_folder
        self.config["secretsFile"] = self.secrets_file
        self.applied_log = AppliedLog(self.output_folder / "applied_log.json")
        self.scheduler: Optional[Scheduler] = None
        self.scheduler_thread: Optional[threading.Thread] = None
        self.run_now_thread: Optional[threading.Thread] = None
        self.run_now_sources: list[str] = []

    def reload_config(self) -> None:
        fresh = ConfigValidator.validate_config(self.config_file)
        self.config.update(fresh)


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
        _ctx = AppContext(_data_folder)
    return _ctx


app = FastAPI(title="CrossJob-AI")


@app.get("/api/status")
def get_status(ctx: AppContext = Depends(get_ctx)) -> dict:
    state = load_state(ctx.output_folder)
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
                "interval_hours": source_config.get("interval_hours"),
                "last_run": entry.get("last_run"),
                "next_run": entry.get("next_run"),
                "status": entry.get("status", "never_run"),
                "last_error": entry.get("last_error"),
                "applied_today": ctx.applied_log.applied_today_count(name),
                "daily_limit": DAILY_APPLICATION_LIMIT,
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


@app.post("/api/settings")
def post_settings(
    body: SourceSettingsUpdate, ctx: AppContext = Depends(get_ctx)
) -> dict:
    if body.source not in dict(ALL_SOURCES):
        raise HTTPException(400, f"Unknown source: {body.source}")
    for field in ("auto_apply", "schedule_enabled", "interval_hours"):
        value = getattr(body, field)
        if value is not None:
            set_source_field(ctx.config_file, body.source, field, value)
    ctx.reload_config()
    return {"source": body.source, "updated": True}


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


if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
