from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Literal

from src.job import Job
from src.job_sources.html_report import render_applications_html
from src.utils.file_lock import state_file_lock

Status = Literal["applied", "dry_run", "skipped_low_fit"]
Period = Literal["day", "week", "month"]


class AppliedLog:
    """История откликов: ключ дедупликации + что было отправлено,
    чтобы по ответу можно было восстановить контекст."""

    def __init__(self, path: Path):
        self.path = path

    @property
    def _data(self) -> dict:
        # ponytail: re-read on every access instead of caching in __init__ —
        # other AppliedLog instances (scheduler thread, other main.py calls)
        # write the same file, so a cached copy goes stale until process
        # restart. The file is small; re-reading it is cheap.
        if self.path.exists():
            return json.loads(self.path.read_text(encoding="utf-8"))
        return {"applications": []}

    def _key(self, job: Job) -> tuple[str, str]:
        return (job.source, job.external_id)

    def _write_locked(self, mutate: Callable[[dict], None]) -> None:
        """Читает актуальные данные с диска под блокировкой (self._data
        теперь всегда читает диск заново, но без блокировки — под ней
        нужна согласованная read-modify-write), применяет mutate() и
        пишет обратно."""
        with state_file_lock(self.path):
            fresh = (
                json.loads(self.path.read_text(encoding="utf-8"))
                if self.path.exists()
                else {"applications": []}
            )
            mutate(fresh)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(fresh, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    def already_applied(self, job: Job) -> bool:
        key = self._key(job)
        return any(
            (e["source"], e["external_id"]) == key
            for e in self._data["applications"]
        )

    def already_applied_to_company(self, job: Job) -> bool:
        """Только реальные (не dry-run) отклики — используется для
        apply_once_at_company, чтобы одна компания с несколькими
        подходящими вакансиями не получала отклики повторно."""
        company = job.company.strip().lower()
        return any(
            e["source"] == job.source
            and e["status"] == "applied"
            and e["company"].strip().lower() == company
            for e in self._data["applications"]
        )

    def applied_today_count(self, source: str) -> int:
        today = datetime.now().astimezone().date()
        return sum(
            1
            for e in self._data["applications"]
            if e["source"] == source
            and e["status"] == "applied"
            and datetime.fromisoformat(e["applied_at"]).date() == today
        )

    def applied_today_count_all(self) -> int:
        """Как applied_today_count(), но сумма по ВСЕМ площадкам —
        для общего дневного лимита на все площадки вместе (main.
        _total_daily_limit_reached()), а не по каждой независимо."""
        today = datetime.now().astimezone().date()
        return sum(
            1
            for e in self._data["applications"]
            if e["status"] == "applied"
            and datetime.fromisoformat(e["applied_at"]).date() == today
        )

    def entries_since(self, source: str, since: datetime) -> list[dict]:
        """Записи по площадке с applied_at >= since — используется для
        сводки воронки отбора за один прогон (main._log_funnel_summary),
        чтобы отличить "записано в этом прогоне" от всей истории."""
        return [
            e
            for e in self._data["applications"]
            if e["source"] == source
            and datetime.fromisoformat(e["applied_at"]) >= since
        ]

    def entries_by_source_and_status(
        self, source: str, status: Status
    ) -> list[dict]:
        return [
            e
            for e in self._data["applications"]
            if e["source"] == source and e["status"] == status
        ]

    def find_by_source_and_external_id(
        self, source: str, external_id: str
    ) -> dict | None:
        for entry in self._data["applications"]:
            if entry["source"] == source and entry["external_id"] == (
                external_id
            ):
                return entry
        return None

    def mark_replied(
        self, source: str, external_id: str, message_id: str
    ) -> None:
        """Запоминает id последнего сообщения работодателя, на
        которое уже отправлен автоответ — чтобы не отвечать на одно
        и то же сообщение повторно на каждый прогон."""

        def _mutate(data: dict) -> None:
            for entry in data["applications"]:
                if (
                    entry["source"] == source
                    and entry["external_id"] == external_id
                ):
                    entry["last_replied_message_id"] = message_id
                    return

        self._write_locked(_mutate)

    def update_reply_state(
        self, source: str, external_id: str, state: str
    ) -> bool:
        """Запоминает последнее увиденное состояние переговоров по
        заявке — возвращает True, если состояние изменилось с
        прошлой проверки (в т.ч. первый раз, когда оно появилось),
        чтобы reply_check.py мог уведомлять только о НОВЫХ ответах, а
        не повторно на каждый запуск check_*_replies."""
        changed = False

        def _mutate(data: dict) -> None:
            nonlocal changed
            for entry in data["applications"]:
                if (
                    entry["source"] == source
                    and entry["external_id"] == external_id
                ):
                    if entry.get("last_known_state") == state:
                        return
                    entry["last_known_state"] = state
                    changed = True
                    return

        self._write_locked(_mutate)
        return changed

    def count_in_period(
        self, period: Period, source: str | None = None
    ) -> int:
        """Реальные (status=applied) отправки с начала сегодняшнего
        дня/этой недели/этого месяца — на этом основана сводка
        статистики день/неделя/месяц."""
        now = datetime.now().astimezone()
        if period == "day":
            since = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "week":
            since = (now - timedelta(days=now.weekday())).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
        else:
            since = now.replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            )
        return sum(
            1
            for e in self._data["applications"]
            if e["status"] == "applied"
            and (source is None or e["source"] == source)
            and datetime.fromisoformat(e["applied_at"]) >= since
        )

    def record(
        self,
        job: Job,
        cover_letter: str,
        resume_id: str,
        status: Status,
        score: int,
        gaps: list[str],
    ) -> None:
        entry = {
            "source": job.source,
            "external_id": job.external_id,
            "company": job.company,
            "title": job.role,
            "link": job.link,
            "salary": job.salary,
            "company_url": job.company_url,
            "cover_letter": cover_letter,
            "resume_id": resume_id,
            "status": status,
            "score": score,
            "gaps": gaps,
            "applied_at": datetime.now().astimezone().isoformat(),
        }

        def _mutate(data: dict) -> None:
            data["applications"].append(entry)

        self._write_locked(_mutate)

        periods: tuple[Period, Period, Period] = ("day", "week", "month")
        stats = {period: self.count_in_period(period) for period in periods}
        report_path = self.path.with_name("applications.html")
        report_path.write_text(
            render_applications_html(
                self._data["applications"], stats, self.most_common_gaps()
            ),
            encoding="utf-8",
        )

    def find_by_company(self, query: str) -> list[dict]:
        needle = query.lower()
        return [
            e
            for e in self._data["applications"]
            if needle in e["company"].lower() or needle in e["title"].lower()
        ]

    def most_common_gaps(self, limit: int = 5) -> list[tuple[str, int]]:
        """Считает частоту повторяющихся формулировок пробелов по
        всем записям — простой Counter без ML, чтобы отчёт показывал
        не только "не подошло", но и почему именно чаще всего."""
        counter: Counter[str] = Counter()
        for entry in self._data["applications"]:
            counter.update(entry.get("gaps") or [])
        return counter.most_common(limit)

    def suggest_blacklist_candidates(self, min_attempts: int = 3) -> list[str]:
        """Компании с min_attempts+ реальными откликами (status=
        applied) и ни одного ответа за всё время — кандидаты для
        company_blacklist в work_preferences.yaml. Только предлагает,
        решение о добавлении — за пользователем.
        ponytail: "без ответа" как прокси для "без успеха" — статус
        переговоров у площадок это свободный текст, который не
        унифицирован настолько, чтобы надёжно отличать позитивный
        ответ от отказа; апгрейд — явная классификация статуса, если
        понадобится точнее."""
        attempts: dict[str, int] = {}
        replied: set[str] = set()
        for entry in self._data["applications"]:
            if entry["status"] != "applied":
                continue
            company = entry["company"]
            attempts[company] = attempts.get(company, 0) + 1
            if entry.get("last_known_state"):
                replied.add(company)
        return sorted(
            company
            for company, count in attempts.items()
            if count >= min_attempts and company not in replied
        )

    def purge_old_cover_letters(self, retention_days: int) -> int:
        """Письмо нужно только на время — свериться, не пишет ли LLM
        чушь (см. config.COVER_LETTER_RETENTION_DAYS) — хранить его
        бессрочно вместе с остальной записью (нужной для дедупликации/
        статистики значительно дольше) незачем. Чистит только сам
        текст cover_letter у старых записей, остальные поля не трогает.
        Возвращает число очищенных записей."""
        cutoff = datetime.now().astimezone() - timedelta(days=retention_days)

        def _is_stale(entry: dict) -> bool:
            return (
                bool(entry.get("cover_letter"))
                and datetime.fromisoformat(entry["applied_at"]) < cutoff
            )

        if not any(_is_stale(e) for e in self._data["applications"]):
            return 0

        purged = 0

        def _mutate(data: dict) -> None:
            nonlocal purged
            for entry in data["applications"]:
                if _is_stale(entry):
                    entry["cover_letter"] = ""
                    purged += 1

        self._write_locked(_mutate)
        return purged
