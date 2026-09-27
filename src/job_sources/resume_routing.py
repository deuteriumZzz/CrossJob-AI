"""Language-aware resume selection for Gmail and Telegram.

The fixed root PDFs remain the safe defaults for email/platform flows.  PDFs
under ``data_folder/telegram`` are a separate pool for quick replies from the
Telegram parser.  ``resume_routing`` in work_preferences.yaml may override any
of the four routes with a relative path from data_folder.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal, Optional

from src.utils.constants import RESUME_PDF, RESUME_PDF_LINKEDIN

ResumeChannel = Literal["email", "telegram"]
ROUTE_KEYS = ("email_ru", "email_en", "telegram_ru", "telegram_en")
_RU_MARKER = re.compile(
    r"(?:^|[_\-.\s])(ru|rus|russian|рус)(?:$|[_\-.\s])", re.I
)


def available_resumes(parameters: dict) -> list[dict]:
    """Return PDFs users may assign to a route, with safe relative names."""
    data_folder = Path(parameters["dataFolder"]).resolve()
    paths = [data_folder / RESUME_PDF, data_folder / RESUME_PDF_LINKEDIN]
    telegram_folder = data_folder / "telegram"
    if telegram_folder.exists():
        paths.extend(sorted(telegram_folder.glob("*.pdf")))
    result = []
    for path in paths:
        if not path.is_file():
            continue
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(data_folder)
        except ValueError:
            continue
        result.append(
            {
                "value": relative.as_posix(),
                "name": path.name,
                "size": path.stat().st_size,
            }
        )
    return result


def _safe_configured_path(parameters: dict, value: object) -> Optional[Path]:
    if not isinstance(value, str) or not value.strip():
        return None
    data_folder = Path(parameters["dataFolder"]).resolve()
    candidate = (data_folder / value).resolve()
    try:
        candidate.relative_to(data_folder)
    except ValueError:
        return None
    if candidate.suffix.lower() != ".pdf" or not candidate.is_file():
        return None
    return candidate


def _telegram_default(parameters: dict, russian: bool) -> Optional[Path]:
    data_folder = Path(parameters["dataFolder"])
    folder = data_folder / "telegram"
    extras = sorted(folder.glob("*.pdf")) if folder.exists() else []
    marked_ru = [p for p in extras if _RU_MARKER.search(p.stem)]
    unmarked = [p for p in extras if p not in marked_ru]
    if russian and marked_ru:
        return marked_ru[0]
    if not russian and unmarked:
        return unmarked[0]
    fallback = data_folder / (RESUME_PDF if russian else RESUME_PDF_LINKEDIN)
    if fallback.is_file():
        return fallback
    other = data_folder / RESUME_PDF
    return other if other.is_file() else (extras[0] if extras else None)


def resolve_resume(
    parameters: dict, channel: ResumeChannel, russian: bool
) -> Optional[Path]:
    """Resolve one of email_ru/email_en/telegram_ru/telegram_en safely."""
    key = f"{channel}_{'ru' if russian else 'en'}"
    if key not in ROUTE_KEYS:
        raise ValueError(f"Unknown resume route: {key}")
    configured = _safe_configured_path(
        parameters, (parameters.get("resume_routing") or {}).get(key)
    )
    if configured is not None:
        return configured
    if channel == "telegram":
        return _telegram_default(parameters, russian)
    data_folder = Path(parameters["dataFolder"])
    preferred = data_folder / (RESUME_PDF if russian else RESUME_PDF_LINKEDIN)
    if preferred.is_file():
        return preferred
    fallback = data_folder / RESUME_PDF
    return fallback if fallback.is_file() else None


def resume_relative_name(parameters: dict, path: Optional[Path]) -> str:
    """Convert a selected PDF to a safe path relative to data_folder."""
    if path is None:
        return ""
    data_folder = Path(parameters["dataFolder"]).resolve()
    candidate = Path(path).resolve()
    try:
        relative = candidate.relative_to(data_folder)
    except ValueError:
        return ""
    return relative.as_posix() if candidate.suffix.lower() == ".pdf" else ""


def resolve_resume_name(parameters: dict, value: object) -> Optional[Path]:
    """Resolve an already stored relative name without permitting traversal."""
    return _safe_configured_path(parameters, value)
