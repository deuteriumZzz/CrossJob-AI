"""Учёт токенов LLM — чтобы расходы на API не были сюрпризом.

Точных $-цен официально нет ни у кого, кроме нескольких известных
моделей OpenAI (см. _OPENAI_PRICING) — для остальных провайдеров/
моделей просто считаем токены без оценки в долларах, чем врать
цифрой. ponytail: цены захардкожены на дату написания, обновлять
вручную при изменении прайса OpenAI.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from src.utils.file_lock import state_file_lock

# $ за 1M токенов (prompt, completion), актуально на 21.08.2026.
_OPENAI_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4-turbo": (10.00, 30.00),
    "gpt-3.5-turbo": (0.50, 1.50),
}

_output_folder: Optional[Path] = None


def set_output_folder(path: Optional[Path]) -> None:
    """Вызывается один раз при старте (main()/AppContext) — get_chat_llm
    не может принимать output_folder явно без правки 8 call sites,
    поэтому глобальная точка, как _data_folder/_ctx в src/webui/api.py."""
    global _output_folder
    _output_folder = path


def get_output_folder() -> Optional[Path]:
    return _output_folder


def _usage_path(output_folder: Path) -> Path:
    return output_folder / ".llm_usage.json"


def record_usage(
    output_folder: Path,
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> None:
    if not prompt_tokens and not completion_tokens:
        return
    path = _usage_path(output_folder)
    with state_file_lock(path):
        data = (
            json.loads(path.read_text(encoding="utf-8"))
            if path.exists()
            else {}
        )
        day = datetime.now(timezone.utc).date().isoformat()
        key = f"{provider}:{model}"
        entry = data.setdefault(day, {}).setdefault(
            key, {"prompt_tokens": 0, "completion_tokens": 0}
        )
        entry["prompt_tokens"] += prompt_tokens
        entry["completion_tokens"] += completion_tokens
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")


def estimate_cost_usd(
    provider: str, model: str, prompt_tokens: int, completion_tokens: int
) -> Optional[float]:
    if provider != "openai":
        return None
    pricing = _OPENAI_PRICING.get(model)
    if not pricing:
        return None
    in_price, out_price = pricing
    return (
        prompt_tokens / 1_000_000 * in_price
        + completion_tokens / 1_000_000 * out_price
    )


def summarize_usage(output_folder: Path) -> dict:
    """Суммарные токены + оценочная $-стоимость (только для известных
    моделей OpenAI — partial=True значит часть звонков не вошла в
    оценку) за сегодня и за всё время."""
    path = _usage_path(output_folder)
    empty = {
        "today_tokens": 0,
        "today_cost_usd": None,
        "total_tokens": 0,
        "total_cost_usd": None,
        "partial": False,
    }
    if not path.exists():
        return empty
    data = json.loads(path.read_text(encoding="utf-8"))
    today = datetime.now(timezone.utc).date().isoformat()

    def _aggregate(days: dict) -> tuple[int, Optional[float], bool]:
        tokens = 0
        known_cost = 0.0
        has_known = False
        has_unknown = False
        for by_model in days.values():
            for key, usage in by_model.items():
                provider, model = key.split(":", 1)
                p, c = usage["prompt_tokens"], usage["completion_tokens"]
                tokens += p + c
                cost = estimate_cost_usd(provider, model, p, c)
                if cost is None:
                    has_unknown = True
                else:
                    has_known = True
                    known_cost += cost
        total_cost = known_cost if has_known else None
        return tokens, total_cost, has_known and has_unknown

    total_tokens, total_cost, total_partial = _aggregate(data)
    today_tokens, today_cost, today_partial = _aggregate(
        {today: data[today]} if today in data else {}
    )
    return {
        "today_tokens": today_tokens,
        "today_cost_usd": today_cost,
        "total_tokens": total_tokens,
        "total_cost_usd": total_cost,
        "partial": total_partial or today_partial,
    }


def _alert_state_path(output_folder: Path) -> Path:
    return output_folder / ".llm_usage_alert.json"


def check_and_mark_alert(output_folder: Path, threshold_usd: float) -> bool:
    """True, если сегодняшняя $-стоимость только что впервые за
    сегодня превысила threshold_usd — вызывающий код должен отправить
    уведомление ровно один раз. До конца дня дальше возвращает False,
    даже если расходы продолжают расти (иначе демон спамил бы
    уведомление на каждом тике, пока порог превышен)."""
    cost = summarize_usage(output_folder)["today_cost_usd"]
    if cost is None or cost < threshold_usd:
        return False
    path = _alert_state_path(output_folder)
    today = datetime.now(timezone.utc).date().isoformat()
    with state_file_lock(path):
        data = (
            json.loads(path.read_text(encoding="utf-8"))
            if path.exists()
            else {}
        )
        if data.get("last_alert_date") == today:
            return False
        data["last_alert_date"] = today
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
    return True


def _health_path(output_folder: Path) -> Path:
    return output_folder / ".llm_health.json"


def record_llm_result(output_folder: Path, ok: bool) -> None:
    """Считает успехи/ошибки LLM-звонков за день — грубый сигнал "все
    провайдеры сегодня недоступны" (обычно значит: исчерпаны
    бесплатные лимиты у всех сразу). Без привязки к конкретному
    провайдеру — with_fallbacks() уже перебирает их все внутри одного
    chain.invoke(), здесь важен только итог всей цепочки."""
    path = _health_path(output_folder)
    with state_file_lock(path):
        data = (
            json.loads(path.read_text(encoding="utf-8"))
            if path.exists()
            else {}
        )
        day = datetime.now(timezone.utc).date().isoformat()
        entry = data.setdefault(day, {"ok": 0, "error": 0})
        entry["ok" if ok else "error"] += 1
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")


def llm_health_today(output_folder: Path) -> dict:
    path = _health_path(output_folder)
    if not path.exists():
        return {"ok": 0, "error": 0}
    data = json.loads(path.read_text(encoding="utf-8"))
    today = datetime.now(timezone.utc).date().isoformat()
    return data.get(today) or {"ok": 0, "error": 0}


def llm_exhausted_today(output_folder: Path) -> bool:
    """Не меньше 3 ошибок за сегодня и ни одного успеха — порог,
    чтобы одна случайная сетевая ошибка в начале дня не поднимала
    тревогу раньше, чем fallback-цепочка вообще успела себя
    показать."""
    health = llm_health_today(output_folder)
    return health["error"] >= 3 and health["ok"] == 0


def check_and_mark_llm_exhausted_alert(output_folder: Path) -> bool:
    """True — впервые за сегодня видно llm_exhausted_today() —
    вызывающий код должен уведомить ровно один раз. Тот же
    debounce-паттерн, что и check_and_mark_alert для расходов (общий
    файл состояния, отдельный ключ)."""
    if not llm_exhausted_today(output_folder):
        return False
    path = _alert_state_path(output_folder)
    today = datetime.now(timezone.utc).date().isoformat()
    with state_file_lock(path):
        data = (
            json.loads(path.read_text(encoding="utf-8"))
            if path.exists()
            else {}
        )
        if data.get("last_llm_exhausted_alert_date") == today:
            return False
        data["last_llm_exhausted_alert_date"] = today
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
    return True


class UsageCallback(BaseCallbackHandler):
    """Подвешивается на LLM в get_chat_llm() — считает токены с
    каждого .invoke()/.generate() автоматически, без правки call
    sites, которые сам LLM вызывают."""

    def __init__(self, output_folder: Path, provider: str, model: str):
        self.output_folder = output_folder
        self.provider = provider
        self.model = model

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs,
    ) -> None:
        record_llm_result(self.output_folder, ok=True)
        usage = (response.llm_output or {}).get("token_usage") or {}
        prompt = usage.get("prompt_tokens", 0)
        completion = usage.get("completion_tokens", 0)
        if prompt or completion:
            record_usage(
                self.output_folder,
                self.provider,
                self.model,
                prompt,
                completion,
            )

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs,
    ) -> None:
        record_llm_result(self.output_folder, ok=False)
