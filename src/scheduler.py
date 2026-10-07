from __future__ import annotations

import inspect
import shutil
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from config import APPLICATION_RETENTION_DAYS, COVER_LETTER_RETENTION_DAYS
from src.job_sources.applied_log import AppliedLog
from src.job_sources.llm_usage import check_and_mark_alert
from src.job_sources.telegram_notify import notify_from_secrets
from src.logging import logger
from src.scheduler_state import (
    get_idle_streak,
    get_next_run,
    load_state,
    record_run_result,
)

DEFAULT_INTERVAL_HOURS = 3
MIN_FREE_DISK_BYTES = 2 * 1024**3

# Площадки, участвующие в "постоянном цикле" (limits.continuous_cycle_enabled)
# — реальный поиск+отклик на job-бордах. telegram — свой живой шлюз
# (посты приходят в момент публикации, ему это не нужно), direct —
# email-рассылка со своим тёмпом (mail_guard), не годится под общий
# 3-минутный круг.
CONTINUOUS_CYCLE_SOURCES = {
    "headhunter",
    "geekjob",
    "getmatch",
    "linkedin",
    "habr_career",
    "wellfound",
    "himalayas",
    "djinni",
    "avito",
    # Чат HH (автоответ, досылка письма, напоминания) — свой ход в том
    # же круге, после площадок, а не прицеп к каждому ходу HH и не
    # отдельный часовой таймер.
    "check_hh_replies",
}


# Предохранитель от зависания: ход площадки в постоянном цикле мягко
# останавливается (через stop_event) по истечении этого времени.
TURN_TIME_LIMIT_SECONDS = 40 * 60

# Пауза до следующего хода площадки, которая N ходов подряд не нашла
# ничего нового (все вакансии уже в журнале): чем дольше пусто, тем реже
# заглядываем. Появилось новое — пауза снова обычная (gap).
IDLE_BACKOFF_HOURS = {2: 0.25, 3: 0.5}
IDLE_BACKOFF_MAX_HOURS = 1.0


def _idle_interval_hours(gap_hours: float, idle_streak: int) -> float:
    if idle_streak < 2:
        return gap_hours
    return max(
        gap_hours, IDLE_BACKOFF_HOURS.get(idle_streak, IDLE_BACKOFF_MAX_HOURS)
    )


# Как часто проверять ответы, если в настройках не задано: команды боту —
# каждые 3 минуты, ответы HR — чаще, чем поиск вакансий.
CHECK_INTERVAL_HOURS = {
    "check_telegram_commands": 0.05,
    "check_telegram_replies": 0.5,
    "check_email_replies": 1,
    "check_hh_replies": 1,
}


class Scheduler:
    """Встроенный планировщик вместо внешнего cron — сам решает,
    когда запускать каждый источник, по schedule_enabled/
    interval_hours в его блоке work_preferences.yaml. Источники сами
    себе ловят PlatformBlockedError через block_detection.py и просто
    молча return'ятся при кулдауне — сюда долетают только реальные
    сбои (сеть, авторизация, баги)."""

    def __init__(
        self,
        source_map: Mapping[str, Callable[..., Any]],
        parameters: dict,
        llm_api_key: str,
        output_folder: Path,
        now_fn: Callable[[], datetime] = datetime.now,
        stop_event: Optional[threading.Event] = None,
    ):
        self.source_map: Mapping[str, Callable[..., Any]] = source_map
        self.parameters = parameters
        self.llm_api_key = llm_api_key
        self.output_folder = output_folder
        self.now_fn = now_fn
        self.stop_event = stop_event or threading.Event()
        self.paused = False
        self._telegram_watcher: Optional[threading.Thread] = None
        self._gateway_failures = 0
        self._gateway_last_try = 0.0
        self._gateway_alerted = 0.0
        self._disk_checked = 0.0
        self._disk_alerted = 0.0
        self._error_alerted: dict[str, float] = {}

    def due_sources(self) -> list[str]:
        if self.paused:
            return []
        due = []
        for name in self.source_map:
            source_config = self.parameters.get(name) or {}
            # Постоянный Telegram-шлюз сам получает каждый новый пост.
            # Пока его поток жив, плановый search_telegram открыл бы
            # второй Telethon-клиент к той же SQLite-сессии. Если шлюз
            # не смог стартовать или уже остановился, поиск остаётся
            # fallback-ом и не пропадает молча.
            if (
                name == "telegram"
                and self._telegram_watcher is not None
                and self._telegram_watcher.is_alive()
            ):
                continue
            # Проверки ответов (check_*) — не площадки, а часть своих каналов:
            # включены по умолчанию и сами ничего не делают, пока канал
            # (Gmail, Telegram, бот) не подключён. Выключить — явным false.
            # hh открывает браузер — только если сама площадка в расписании.
            enabled_by_default = name.startswith("check_") and (
                name != "check_hh_replies"
                or bool(
                    (self.parameters.get("headhunter") or {}).get(
                        "schedule_enabled"
                    )
                )
            )
            enabled = source_config.get("schedule_enabled", enabled_by_default)
            # В постоянном цикле чат HH — часть хода HH по кругу и следует
            # галочке самого HH (как раньше прицеп к его ходу), а не своей.
            if name == "check_hh_replies" and self._continuous():
                enabled = bool(
                    (self.parameters.get("headhunter") or {}).get(
                        "schedule_enabled"
                    )
                )
            if not enabled:
                continue
            next_run = get_next_run(self.output_folder, name)
            if next_run is None or next_run <= self.now_fn():
                due.append(name)
        return due

    def _seen_count(self, name: str) -> int:
        return len(
            AppliedLog(self.output_folder / "applied_log.json").seen_ids(name)
        )

    def _call_source(self, name: str, platform_turn: bool) -> None:
        """Запуск источника; ход площадки в постоянном цикле получает
        stop_event, который сам срабатывает через TURN_TIME_LIMIT_SECONDS."""
        fn = self.source_map[name]
        if (
            not platform_turn
            or "stop_event" not in inspect.signature(fn).parameters
        ):
            fn(self.parameters, self.llm_api_key)
            return
        stop = threading.Event()
        timer = threading.Timer(TURN_TIME_LIMIT_SECONDS, stop.set)
        timer.daemon = True
        timer.start()
        try:
            fn(self.parameters, self.llm_api_key, stop_event=stop)
        finally:
            timer.cancel()

    def _supervise_gateway(self) -> None:
        """Шлюз Telegram сам поднимается, если поток умер (раньше он жил и
        гас только вместе с планировщиком). Не чаще раза в 30 секунд; после
        3 неудач подряд — одно сообщение в Telegram (не чаще раза в час)."""
        from src.job_sources.telegram.watcher import (
            active_watcher,
            start_telegram_watcher,
        )

        if not (self.parameters.get("telegram") or {}).get("watch_enabled"):
            return
        w = self._telegram_watcher
        if (w is not None and w.is_alive()) or active_watcher() is not None:
            self._gateway_failures = 0
            return
        now = self.now_fn().timestamp()
        if now - self._gateway_last_try < 30:
            return
        self._gateway_last_try = now
        try:
            self._telegram_watcher = start_telegram_watcher(
                self.parameters, self.llm_api_key
            )
            logger.info("Telegram-шлюз перезапущен надзором.")
        except Exception as e:
            self._gateway_failures += 1
            logger.warning(f"Telegram-шлюз не поднялся: {e}")
            if (
                self._gateway_failures >= 3
                and now - self._gateway_alerted > 3600
            ):
                self._gateway_alerted = now
                notify_from_secrets(
                    self.parameters,
                    "CrossJob-AI: Telegram-шлюз не поднимается "
                    f"({self._gateway_failures} попытки подряд): {e}",
                )

    def _check_disk_space(self) -> None:
        """Раз в час проверяет свободное место: при <2 ГБ — одно сообщение
        в сутки (на 2.10 нехватка места молча роняла Telegram-шлюз)."""
        now = self.now_fn().timestamp()
        if now - self._disk_checked < 3600:
            return
        self._disk_checked = now
        try:
            free = shutil.disk_usage(self.output_folder).free
        except OSError:
            return
        if free < MIN_FREE_DISK_BYTES and now - self._disk_alerted > 86400:
            self._disk_alerted = now
            notify_from_secrets(
                self.parameters,
                "CrossJob-AI: на диске осталось "
                f"{free / 1024**3:.1f} ГБ — при нехватке места падают шлюз "
                "Telegram и браузеры. Освободите место.",
            )

    def _check_shared_errors(self) -> None:
        """Одна и та же ошибка у трёх и более площадок за последние 3 часа —
        значит, ломается общее (ключ ИИ, браузер, сеть), а не одна площадка:
        одно сообщение на такую ошибку в сутки."""
        now = self.now_fn()
        since = now - timedelta(hours=3)
        by_error: dict[str, list[str]] = {}
        for name, entry in load_state(self.output_folder).items():
            if entry.get("status") != "error" or not entry.get("last_error"):
                continue
            try:
                last = datetime.fromisoformat(entry.get("last_run") or "")
            except ValueError:
                continue
            if last.tzinfo is None and since.tzinfo is not None:
                last = last.astimezone()
            if last < since:
                continue
            key = " ".join(str(entry["last_error"]).split())[:80]
            by_error.setdefault(key, []).append(name)
        for key, names in by_error.items():
            stamp = now.timestamp()
            if (
                len(names) >= 3
                and stamp - self._error_alerted.get(key, 0.0) > 86400
            ):
                self._error_alerted[key] = stamp
                notify_from_secrets(
                    self.parameters,
                    f"CrossJob-AI: одна ошибка у {len(names)} площадок "
                    f"({', '.join(sorted(names))}): {key}",
                )

    def _continuous(self) -> bool:
        limits = self.parameters.get("limits") or {}
        return bool(limits.get("continuous_cycle_enabled"))

    def run_once(self) -> None:
        from src.utils.backup import daily_backup

        daily_backup(self.output_folder)
        limits = self.parameters.get("limits") or {}
        continuous = self._continuous()
        gap_hours = (
            max(1, int(limits.get("continuous_cycle_gap_minutes", 3))) / 60
        )

        due = self.due_sources()
        if continuous:
            # Раунд-робин через уже существующий next_run каждой площадки:
            # за один тик запускается одна due-площадка из круга — её
            # next_run сдвинется на gap_hours вперёд, и на следующем тике
            # (30с) ход у следующей. Остальные check_*-задачи (ответы HR в
            # почте/Telegram и т.п.) в круг не входят — идут своим чередом.
            due_cycle = [n for n in due if n in CONTINUOUS_CYCLE_SOURCES]
            due_rest = [n for n in due if n not in CONTINUOUS_CYCLE_SOURCES]
            # Ход — тому, кто ждёт дольше всех (самый старый next_run), а
            # не первому по порядку: прогон HH длится дольше gap, к его
            # концу HH снова due и снова первый — живой инцидент, getmatch/
            # linkedin/habr и др. не запускались 4 дня подряд.
            waits = {n: get_next_run(self.output_folder, n) for n in due_cycle}
            due_cycle.sort(key=lambda n: (waits[n] is not None, waits[n] or 0))
            due = due_rest + (due_cycle[:1] if due_cycle else [])

        for name in due:
            run_at = self.now_fn()
            interval_hours = (
                gap_hours
                if continuous and name in CONTINUOUS_CYCLE_SOURCES
                else (self.parameters.get(name) or {}).get(
                    "interval_hours",
                    CHECK_INTERVAL_HOURS.get(name, DEFAULT_INTERVAL_HOURS),
                )
            )
            next_run = run_at + timedelta(hours=interval_hours)
            platform_turn = (
                continuous
                and name in CONTINUOUS_CYCLE_SOURCES
                and name != "check_hh_replies"
            )
            seen_before = self._seen_count(name) if platform_turn else 0
            try:
                self._call_source(name, platform_turn)
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
            idle_streak: Optional[int] = None
            if platform_turn:
                idle_streak = (
                    get_idle_streak(self.output_folder, name) + 1
                    if self._seen_count(name) == seen_before
                    else 0
                )
                interval_hours = _idle_interval_hours(gap_hours, idle_streak)
            next_run = run_at + timedelta(hours=interval_hours)
            record_run_result(
                self.output_folder,
                name,
                "ok",
                next_run,
                run_at,
                idle_streak=idle_streak,
            )

        self._check_llm_cost_alert()
        self._purge_old_cover_letters()
        self._purge_old_applications()

    def _purge_old_cover_letters(self) -> None:
        retention_days = int(
            (self.parameters.get("limits") or {}).get(
                "cover_letter_retention_days", COVER_LETTER_RETENTION_DAYS
            )
        )
        applied_log = AppliedLog(self.output_folder / "applied_log.json")
        purged = applied_log.purge_old_cover_letters(retention_days)
        if purged:
            logger.info(
                f"Cover letter cleanup: cleared {purged} letter(s) older "
                f"than {retention_days}d."
            )

    def _purge_old_applications(self) -> None:
        retention_days = int(
            (self.parameters.get("limits") or {}).get(
                "application_retention_days", APPLICATION_RETENTION_DAYS
            )
        )
        applied_log = AppliedLog(self.output_folder / "applied_log.json")
        removed = applied_log.purge_old_applications(retention_days)
        if removed:
            logger.info(
                f"Application history cleanup: removed {removed} "
                f"record(s) older than {retention_days}d."
            )

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
        from src.job_sources.telegram.watcher import (
            active_watcher,
            start_telegram_watcher,
        )

        logger.info("Scheduler started.")
        # Постоянный шлюз Telegram (telegram.watch_enabled) живёт, пока
        # живёт демон: новые посты каналов приходят сразу, без расписания.
        try:
            watcher = start_telegram_watcher(self.parameters, self.llm_api_key)
        except Exception as e:
            logger.warning(f"Telegram-шлюз не запустился: {e}")
            watcher = None
        self._telegram_watcher = watcher
        try:
            while not self.stop_event.is_set():
                # Неожиданная ошибка одного тика не должна останавливать
                # демон: вместе с ним гасло и постоянное соединение с
                # Telegram (живьём 3–7 октября шлюз «обрывался» именно так).
                try:
                    self.run_once()
                except Exception as e:
                    logger.exception(f"[scheduler] тик упал, продолжаю: {e}")
                self._supervise_gateway()
                self._check_disk_space()
                self._check_shared_errors()
                self.stop_event.wait(tick_seconds)
        finally:
            # Парсер могли включить/выключить из дашборда на ходу — гасим
            # тот, что работает сейчас, а не только запущенный здесь.
            for w in (watcher, active_watcher()):
                if w is not None:
                    w.stop()
            self._telegram_watcher = None
            logger.info("Scheduler stopped.")
