"""Предзаполнение формы отклика на сайте компании (Greenhouse, Lever):
стандартные поля, резюме и письмо. Вопросы компании и кнопку отправки
оставляем человеку — на отправке у обеих систем капча (Greenhouse —
невидимая reCAPTCHA Enterprise, Lever — hCaptcha; проверено 2026-09-24),
её бот не проходит. Разметка полей тоже проверена вживую в тот день."""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

from selenium.webdriver.common.by import By

PAGE_LOAD_WAIT_SECONDS = 5


def _fill(driver, selector: str, value: str) -> bool:
    if not value:
        return False
    fields = driver.find_elements(By.CSS_SELECTOR, selector)
    if not fields:
        return False
    field = fields[0]
    is_file = field.get_attribute("type") == "file"
    if not is_file and field.get_attribute("value"):
        return False  # уже заполнено (браузер/пользователь) — не трогаем
    field.send_keys(value)
    if is_file:
        # Greenhouse загружает файл и перерисовывает форму — старый
        # элемент после этого "протухает", поэтому тип читаем заранее.
        time.sleep(3)
    return True


def _cover_letter_file(cover_letter: str) -> str:
    path = Path(tempfile.mkdtemp()) / "cover_letter.txt"
    path.write_text(cover_letter, encoding="utf-8")
    return str(path)


def prefill_application(
    driver,
    job_link: str,
    person: dict,
    resume_pdf: Path,
    cover_letter: str,
) -> list[str]:
    """Открывает форму и заполняет, что знает. Возвращает список
    заполненных полей (пустой — форма не распознана)."""
    phone = f"{person.get('phone_prefix', '')}{person.get('phone', '')}"
    full_name = f"{person.get('name', '')} {person.get('surname', '')}".strip()
    location = ", ".join(filter(None, [person.get("city"), person.get("country")]))

    if "greenhouse.io" in job_link:
        driver.get(job_link)
        fields = [
            ("first_name", "#first_name", person.get("name", "")),
            ("last_name", "#last_name", person.get("surname", "")),
            ("email", "#email", person.get("email", "")),
            ("phone", "#phone", phone),
            ("resume", "input#resume[type=file]", str(resume_pdf)),
            (
                "cover_letter",
                "input#cover_letter[type=file]",
                _cover_letter_file(cover_letter) if cover_letter else "",
            ),
        ]
    elif "lever.co" in job_link:
        apply_url = job_link.rstrip("/")
        if not apply_url.endswith("/apply"):
            apply_url += "/apply"
        driver.get(apply_url)
        fields = [
            ("resume", "input[name=resume][type=file]", str(resume_pdf)),
            ("name", "input[name=name]", full_name),
            ("email", "input[name=email]", person.get("email", "")),
            ("phone", "input[name=phone]", phone),
            ("location", "input[name=location]", location),
            ("linkedin", 'input[name="urls[LinkedIn]"]', person.get("linkedin", "")),
            ("github", 'input[name="urls[GitHub]"]', person.get("github", "")),
            ("cover_letter", "textarea[name=comments]", cover_letter),
        ]
    else:
        driver.get(job_link)
        return []

    time.sleep(PAGE_LOAD_WAIT_SECONDS)
    filled: list[str] = []
    for name, selector, value in fields:
        try:
            if _fill(driver, selector, value):
                filled.append(name)
        except Exception:
            continue  # одно поле не заполнилось — остальные всё равно
    return filled
