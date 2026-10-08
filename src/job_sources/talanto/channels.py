"""Telegram-каналы из вакансий Talanto → в список парсера.

Talanto — сборщик: если в вакансии есть Telegram-канал с вакансиями, он
становится ещё одним источником нашего Telegram-парсера (telegram.channels).
Личные адреса рекрутёров в парсер не идут (они постов не публикуют) —
остаются в Базе. Канал это или человек, узнаём у Telegram через ваш
аккаунт; результат запоминается, чтобы не спрашивать повторно."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import yaml

from src.config_patch import set_source_list_field
from src.job_sources.telegram.client import (
    TelegramSourceClient,
    normalize_channel,
)
from src.logging import logger

CACHE_FILE = ".talanto_tg_handles.json"
# За ход спрашиваем у Telegram не больше стольких новых адресов (флуд-лимиты).
MAX_LOOKUPS_PER_RUN = 10


def _load(path: Path) -> dict[str, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def route_telegram_handles(
    parameters: dict[str, Any],
    handles: list[str],
    client_factory: Optional[Any] = None,
) -> list[str]:
    """Каналы из handles, которые добавили в telegram.channels. Без
    настроенного Telegram (ключи, вход) — ничего не делает и не падает."""
    output_folder: Path = parameters["outputFileDirectory"]
    config_file: Path = parameters["dataFolder"] / "work_preferences.yaml"
    try:
        secrets = yaml.safe_load(
            Path(parameters["secretsFile"]).read_text(encoding="utf-8")
        )
    except (OSError, yaml.YAMLError):
        return []
    telegram = (secrets or {}).get("telegram") or {}
    api_id, api_hash = telegram.get("api_id"), telegram.get("api_hash")
    session = output_folder / ".telegram_session.session"
    if not (api_id and api_hash and session.exists()):
        return []

    existing = list((parameters.get("telegram") or {}).get("channels") or [])
    known = {normalize_channel(c).lower() for c in existing}
    cache_path = output_folder / CACHE_FILE
    cache = _load(cache_path)

    fresh: list[str] = []
    for raw in handles:
        name = normalize_channel(raw)
        if name and name.lower() not in known and name not in fresh:
            fresh.append(name)
    to_ask = [n for n in fresh if n not in cache][:MAX_LOOKUPS_PER_RUN]

    if to_ask:
        factory = client_factory or (
            lambda: TelegramSourceClient(
                int(api_id), api_hash, output_folder / ".telegram_session"
            )
        )
        try:
            with factory() as client:
                for name in to_ask:
                    try:
                        kind = client.entity_kind(name)
                    except Exception as e:
                        logger.warning(f"Talanto: @{name} не определён: {e}")
                        continue
                    if kind:  # None — сбой, спросим в следующий раз
                        cache[name] = kind
        except Exception as e:
            logger.warning(f"Talanto: Telegram недоступен для проверки: {e}")
        cache_path.write_text(
            json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    added = [n for n in fresh if cache.get(n) == "channel"]
    if added:
        set_source_list_field(
            config_file, "telegram", "channels", existing + added
        )
        logger.info(
            "Talanto: каналы добавлены в парсер: "
            + ", ".join(f"@{n}" for n in added)
        )
    return added
