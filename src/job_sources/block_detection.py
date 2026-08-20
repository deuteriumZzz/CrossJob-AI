from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

BLOCK_COOLDOWN_HOURS = 24
_BLOCK_KEYWORDS = ("captcha", "подозрительная активность")


class PlatformBlockedError(Exception):
    """Площадка вернула капчу/бан вместо обычного ответа."""


def raise_if_blocked(response_or_html) -> None:
    """Принимает либо httpx.Response (проверяет status_code + text),
    либо голую HTML/текстовую строку (например driver.page_source)."""
    status_code = getattr(response_or_html, "status_code", None)
    text = getattr(response_or_html, "text", response_or_html) or ""
    if status_code == 429:
        raise PlatformBlockedError(f"HTTP 429 (rate limited): {text[:200]}")
    lowered = text.lower()
    for keyword in _BLOCK_KEYWORDS:
        if keyword in lowered:
            raise PlatformBlockedError(
                f"Blocked (detected {keyword!r} in response body)"
            )


def _blocked_until_path(output_folder: Path) -> Path:
    return output_folder / ".blocked_until.json"


def mark_blocked(output_folder: Path, source: str) -> None:
    """Отмечает источник как заблокированный на BLOCK_COOLDOWN_HOURS —
    следующий запуск (в т.ч. из cron) пропустит его вместо того,
    чтобы долбить капчу повторно."""
    path = _blocked_until_path(output_folder)
    data = (
        json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    )
    until = datetime.now().astimezone() + timedelta(hours=BLOCK_COOLDOWN_HOURS)
    data[source] = until.isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def is_still_blocked(output_folder: Path, source: str) -> bool:
    path = _blocked_until_path(output_folder)
    if not path.exists():
        return False
    data = json.loads(path.read_text(encoding="utf-8"))
    until_str = data.get(source)
    if not until_str:
        return False
    return datetime.now().astimezone() < datetime.fromisoformat(until_str)
