from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from src.utils.file_lock import state_file_lock

BLOCK_COOLDOWN_HOURS = 24
# ponytail: "captcha"/"подозрительная активность" ловили не всякую
# капчу вживую (см. инцидент — hh.ru показал капчу, эти два слова не
# совпали, детект молчал, демон продолжал долбить). Точный текст той
# капчи неизвестен — вместо него более широкий набор типичных фраз
# антибот-страниц (Yandex SmartCaptcha/reCAPTCHA/общие формулировки).
# Каждая — не одно слово (риск ложных срабатываний на реальных
# вакансиях вроде "инженер по робототехнике"), а достаточно
# специфичная фраза; всё равно не проверено на конкретной капче,
# которую видел пользователь — обновить, если она попадётся снова.
_BLOCK_KEYWORDS = (
    "captcha",
    "подозрительная активность",
    "подтвердите, что вы не робот",
    "вы не робот",
    "докажите, что вы человек",
    "smartcaptcha",
    "unusual traffic",
    "verify you are a human",
    "confirm you are not a robot",
    "доступ ограничен",
    "access denied",
)


class PlatformBlockedError(Exception):
    """Площадка вернула капчу/бан вместо обычного ответа."""


def raise_if_blocked(response_or_html) -> None:
    """Принимает либо httpx.Response (проверяет status_code + text),
    либо голую HTML/текстовую строку. Для Selenium-страниц сюда нужно
    передавать visible_text(driver), а не driver.page_source — см. её
    докстринг."""
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


def visible_text(driver) -> str:
    """Тяжёлые SPA (Next.js и т.п.) тянут в driver.page_source
    мегабайты встроенных JS/CSS-бандлов — подтверждено на живых
    аккаунтах дважды: на hh.ru там буквально есть строка
    "error.signup.captcha.invalid":"Please, confirm that you are not
    a robot" (словарь переводов), на getmatch.ru — класс
    ".SmartCaptcha-Overlay" (стили виджета капчи, подгружаются
    заранее независимо от того, показана ли капча реально). Оба раза
    это вызывало ложное срабатывание raise_if_blocked на самой
    обычной странице. Проверять на капчу/блокировку нужно то, что
    видит пользователь, а не сырой HTML целиком — отсюда именно
    document.body.innerText, а не page_source."""
    return driver.execute_script("return document.body.innerText") or ""


def _blocked_until_path(output_folder: Path) -> Path:
    return output_folder / ".blocked_until.json"


def mark_blocked(output_folder: Path, source: str) -> None:
    """Отмечает источник как заблокированный на BLOCK_COOLDOWN_HOURS —
    следующий запуск (в т.ч. из cron) пропустит его вместо того,
    чтобы долбить капчу повторно."""
    path = _blocked_until_path(output_folder)
    with state_file_lock(path):
        data = (
            json.loads(path.read_text(encoding="utf-8"))
            if path.exists()
            else {}
        )
        until = datetime.now().astimezone() + timedelta(
            hours=BLOCK_COOLDOWN_HOURS
        )
        data[source] = until.isoformat()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def clear_blocked(output_folder: Path, source: str) -> None:
    """Снимает блокировку раньше 24ч-кулдауна — вызывается, когда
    пользователь вручную решил капчу в персистентном Chrome-профиле и
    прислал /resume <площадка> в Telegram (см. check_telegram_commands
    в main.py). Без реальной блокировки (source не в .blocked_until.json)
    просто ничего не делает."""
    path = _blocked_until_path(output_folder)
    with state_file_lock(path):
        if not path.exists():
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.pop(source, None) is not None:
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
