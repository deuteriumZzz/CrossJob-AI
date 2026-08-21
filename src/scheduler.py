from __future__ import annotations

import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

from src.job_sources.llm_usage import check_and_mark_alert
from src.job_sources.telegram_notify import notify_from_secrets
from src.logging import logger
from src.scheduler_state import get_next_run, record_run_result

DEFAULT_INTERVAL_HOURS = 3


class Scheduler:
    """Встроенный планировщик вместо внешнего cron — сам решает,
    когда запускать каждый источник, по schedule_enabled/
    interval_hours в его блоке work_preferences.yaml. Источники сами
    себе ловят PlatformBlockedError через block_detection.py и просто
    молча return'ятся при кулдауне — сюда долетают только реальные
    сбои (сеть, авторизация, баги)."""

    def __init__(
        self,
        source_map: dict[str, Callable[[dict, str], None]],
        parameters: dict,
        llm_api_key: str,
        output_folder: Path,
        now_fn: Callable[[], datetime] = datetime.now,
        stop_event: Optional[threading.Event] = None,
    ):
        self.source_map = source_map
        self.parameters = parameters
        self.llm_api_key = llm_api_key
        self.output_folder = output_folder
        self.now_fn = now_fn
        self.stop_event = stop_event or threading.Event()

    def due_sources(self) -> list[str]:
        due = []
        for name in self.source_map:
            source_config = self.parameters.get(name) or {}
            if not source_config.get("schedule_enabled"):
                continue
            next_run = get_next_run(self.output_folder, name)
            if next_run is None or next_run <= self.now_fn():
                due.append(name)
        return due

    def run_once(self) -> None:
        for name in self.due_sources():
            run_at = self.now_fn()
            interval_hours = (self.parameters.get(name) or {}).get(
                "interval_hours", DEFAULT_INTERVAL_HOURS
            )
            next_run = run_at + timedelta(hours=interval_hours)
            try:
                self.source_map[name](self.parameters, self.llm_api_key)
            except Exception as e:
                logger.exception(f"[scheduler] {name} failed: {e}")
                record_run_result(
                    self.output_folder,
                    name,
                    "error",
                    next_run,
                    run_at,
                    error=str(e),
                )
                notify_from_secrets(
                    self.parameters,
                    f"CrossJob-AI (демон): {name} упал во время "
                    f"планового запуска — {e}",
                )
                continue
            record_run_result(self.output_folder, name, "ok", next_run, run_at)

        self._check_llm_cost_alert()

    def _check_llm_cost_alert(self) -> None:
        threshold = (self.parameters.get("limits") or {}).get(
            "llm_daily_cost_alert_usd"
        )
        if not threshold:
            return
        if check_and_mark_alert(self.output_folder, float(threshold)):
            notify_from_secrets(
                self.parameters,
                f"CrossJob-AI: расходы на LLM сегодня превысили "
                f"${threshold}.",
            )

    def stop(self) -> None:
        self.stop_event.set()

    def run_forever(self, tick_seconds: int = 30) -> None:
        logger.info("Scheduler started.")
        try:
            while not self.stop_event.is_set():
                self.run_once()
                self.stop_event.wait(tick_seconds)
        finally:
            logger.info("Scheduler stopped.")
