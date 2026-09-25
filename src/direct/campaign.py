"""Рассылка по базе контактов: берём компании с email, которым ещё не
писали (из вашего файла, Telegram, вакансий — база одна), готовим
письма по промту (кто я → почему вы → 2–3 достижения → звонок), вы их
просматриваете во «Входящих», потом бот шлёт по одному через Gmail с
паузами и дневным лимитом, резюме во вложении. Статусы по каждому
адресу: черновик → отправлено / ошибка (с причиной) / возврат / ответили."""

from __future__ import annotations

import json
import random
import secrets
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from src.utils.file_lock import state_file_lock

CAMPAIGNS_FILE = "campaigns.json"
STATUSES = ("pending", "draft", "sent", "failed", "bounced", "replied", "skipped")
PAUSE_SECONDS = (60, 120)  # между письмами — чтобы Gmail не счёл рассылкой


class CampaignStore:
    def __init__(self, output_folder: Path):
        self.path = output_folder / CAMPAIGNS_FILE

    def _load(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def all(self) -> dict:
        return self._load()

    def get(self, campaign_id: str) -> Optional[dict]:
        return self._load().get(campaign_id)

    def create(self, name: str, targets: list[dict]) -> str:
        """targets: [{key, email, company}] — одна строка на адрес."""
        campaign_id = secrets.token_hex(3)
        with state_file_lock(self.path):
            data = self._load()
            data[campaign_id] = {
                "id": campaign_id,
                "name": name,
                "created_at": datetime.now().astimezone().isoformat(),
                "items": {
                    t["email"].lower(): {
                        "key": t["key"], "company": t["company"],
                        "status": "pending", "reason": "", "code": "", "sent_at": "",
                    }
                    for t in targets
                },
            }
            self._save(data)
        return campaign_id

    def update_item(self, campaign_id: str, email: str, **fields) -> None:
        with state_file_lock(self.path):
            data = self._load()
            item = data.get(campaign_id, {}).get("items", {}).get(email.lower())
            if item is not None:
                item.update(fields)
                self._save(data)

    def add_items(self, campaign_id: str, targets: list[dict]) -> int:
        """Дописать адреса в очередь идущей рассылки (новые компании Базы).
        Возвращает, сколько добавлено."""
        added = 0
        with state_file_lock(self.path):
            data = self._load()
            items = data.get(campaign_id, {}).get("items")
            if items is None:
                return 0
            for t in targets:
                email = t["email"].lower()
                if email not in items:
                    items[email] = {"key": t["key"], "company": t["company"],
                                    "status": "pending", "reason": "", "code": "", "sent_at": ""}
                    added += 1
            self._save(data)
        return added

    def update(self, campaign_id: str, **fields) -> None:
        """Поля самой рассылки (например, день последней порции писем)."""
        with state_file_lock(self.path):
            data = self._load()
            if campaign_id in data:
                data[campaign_id].update(fields)
                self._save(data)

    def emails_with_status(self, *statuses: str) -> set[str]:
        return {
            email
            for c in self._load().values()
            for email, item in c["items"].items()
            if item["status"] in statuses
        }

    def delete(self, campaign_id: str) -> None:
        with state_file_lock(self.path):
            data = self._load()
            data.pop(campaign_id, None)
            self._save(data)


def campaign_stats(campaign: dict) -> dict:
    counts = {status: 0 for status in STATUSES}
    for item in campaign["items"].values():
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    counts["total"] = len(campaign["items"])
    return counts


class CampaignJob(threading.Thread):
    """Фоновая работа по кампании: подготовка писем или отправка — по
    одному адресу за шаг. step(email) → None (дальше) или причина
    остановки (например, «дневной лимит»). pause — пауза между письмами."""

    RUNNING: dict[str, "CampaignJob"] = {}

    def __init__(
        self,
        campaign_id: str,
        kind: str,
        emails: list[str],
        step: Callable[[str], Optional[str]],
        pause: "bool | Callable[[], float]",
        on_finish: Optional[Callable[["CampaignJob"], None]] = None,
    ):
        super().__init__(name=f"campaign-{campaign_id}-{kind}", daemon=True)
        self.campaign_id, self.kind = campaign_id, kind
        self.emails, self.step, self.pause = emails, step, pause
        self.on_finish = on_finish
        self.done = 0
        self.message = ""
        self.next_at = 0.0  # когда следующее письмо (time.time()) — для «через ~N мин»
        self._stopping = threading.Event()

    def stop(self) -> None:
        self._stopping.set()

    def run(self) -> None:
        self.RUNNING[self.campaign_id] = self
        try:
            for index, email in enumerate(self.emails):
                if self._stopping.is_set():
                    self.message = "Остановлено"
                    break
                reason = self.step(email)
                self.done += 1
                if reason:
                    self.message = reason
                    break
                last = index == len(self.emails) - 1
                # pause — True (1–2 мин) или функция, считающая «человеческую» паузу.
                seconds = (self.pause() if callable(self.pause) else random.randint(*PAUSE_SECONDS)) if self.pause else 0
                self.next_at = time.time() + seconds
                if self.pause and not last and self._stopping.wait(seconds):
                    self.message = "Остановлено"
                    break
            else:
                self.message = "Готово"
        finally:
            self.RUNNING.pop(self.campaign_id, None)
            if self.on_finish is not None:
                self.on_finish(self)

    @classmethod
    def progress(cls, campaign_id: str) -> Optional[dict]:
        job = cls.RUNNING.get(campaign_id)
        if job is None:
            return None
        return {"kind": job.kind, "done": job.done, "total": len(job.emails),
                "next_in": max(0, int(job.next_at - time.time())) if job.next_at else 0}
