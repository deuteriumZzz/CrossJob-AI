from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from src.job import Job
from src.job_sources.html_report import render_applications_html

Status = Literal["applied", "dry_run", "skipped_low_fit"]
Period = Literal["day", "week", "month"]


class AppliedLog:
    """История откликов: ключ дедупликации + что было отправлено,
    чтобы по ответу можно было восстановить контекст."""

    def __init__(self, path: Path):
        self.path = path
        if self.path.exists():
            self._data = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self._data = {"applications": []}

    def _key(self, job: Job) -> tuple[str, str]:
        return (job.source, job.external_id)

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

    def entries_by_source_and_status(
        self, source: str, status: Status
    ) -> list[dict]:
        return [
            e
            for e in self._data["applications"]
            if e["source"] == source and e["status"] == status
        ]

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
        self, job: Job, cover_letter: str, resume_id: str, status: Status
    ) -> None:
        self._data["applications"].append(
            {
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
                "applied_at": datetime.now().astimezone().isoformat(),
            }
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        periods: tuple[Period, Period, Period] = ("day", "week", "month")
        stats = {period: self.count_in_period(period) for period in periods}
        report_path = self.path.with_name("applications.html")
        report_path.write_text(
            render_applications_html(self._data["applications"], stats),
            encoding="utf-8",
        )

    def find_by_company(self, query: str) -> list[dict]:
        needle = query.lower()
        return [
            e
            for e in self._data["applications"]
            if needle in e["company"].lower() or needle in e["title"].lower()
        ]
