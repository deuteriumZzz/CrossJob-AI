"""Офферы для сравнения в дашборде (Аналитика → Сравнение офферов):
сумма в месяц, валюта, удалёнка, заметки — плюс сравнение с медианой
рынка по собранным вакансиям в той же валюте.
ponytail: без пересчёта валют и налогов — разные страны/режимы
считаются по-разному; сравнение идёт внутри одной валюты."""

from __future__ import annotations

import json
import secrets
from datetime import datetime
from pathlib import Path

OFFERS_FILE = "offers.json"


def load_offers(output_folder: Path) -> list[dict]:
    path = output_folder / OFFERS_FILE
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def save_offers(output_folder: Path, offers: list[dict]) -> None:
    (output_folder / OFFERS_FILE).write_text(
        json.dumps(offers, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def add_offer(output_folder: Path, offer: dict) -> dict:
    offer = {
        **offer,
        "id": secrets.token_hex(2),
        "added_at": datetime.now().astimezone().isoformat(),
    }
    save_offers(output_folder, load_offers(output_folder) + [offer])
    return offer


def compare_with_market(offers: list[dict], market: list[dict]) -> list[dict]:
    """К каждому офферу — отклонение от медианы "до" рынка в той же
    валюте, в процентах (None, если по валюте нет данных)."""
    medians = {row["currency"]: row["median_max"] for row in market}
    result = []
    for offer in sorted(offers, key=lambda o: -o["amount"]):
        median = medians.get(offer["currency"])
        result.append(
            {
                **offer,
                "vs_market": (
                    round((offer["amount"] / median - 1) * 100)
                    if median
                    else None
                ),
            }
        )
    return result
