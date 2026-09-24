"""Список целевых компаний модуля «Прямой поиск», которым управляет
дашборд (Настройки → Компании). Отдельный файл, а не work_preferences.yaml,
чтобы не переписывать комментарии пользователя в YAML. Компании,
прописанные вручную в direct.companies, тоже учитываются."""

from __future__ import annotations

import json
from pathlib import Path

COMPANIES_FILE = "direct_companies.json"


def load_companies(data_folder: Path) -> list[dict]:
    path = data_folder / COMPANIES_FILE
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def save_companies(data_folder: Path, companies: list[dict]) -> None:
    (data_folder / COMPANIES_FILE).write_text(
        json.dumps(companies, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def all_companies(parameters: dict) -> list[dict]:
    manual = (parameters.get("direct") or {}).get("companies") or []
    return list(manual) + load_companies(parameters["dataFolder"])
