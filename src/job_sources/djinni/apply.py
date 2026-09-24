"""Вход и отклик на djinni.co через браузер с постоянным профилем.

Вход — только вручную в открывшемся окне (бот не вводит пароль и не
создаёт аккаунт). Отклик на Djinni — это сообщение рекрутеру плюс ваш
профиль с CV на сайте; сообщением уходит сопроводительное письмо.

ponytail: форма отклика видна только залогиненным — разметку до первого
живого прогона подтвердить нельзя. Поэтому кнопки ищутся по тексту на
трёх языках интерфейса, а не по классам вёрстки, и первый запуск идёт в
режиме «Только ищет». Если отклик не подтвердился — вакансия пишется как
dry_run, а не как отправленная."""

from __future__ import annotations

import time
from pathlib import Path

from selenium.webdriver.common.by import By

from src.job_sources.block_detection import raise_if_blocked, visible_text
from src.job_sources.telegram_notify import notify_manual_login_required
from src.logging import logger
from src.utils.chrome_utils import get_with_retry, init_browser

BASE = "https://djinni.co"
LOGIN_TIMEOUT_SECONDS = 600
PAGE_LOAD_WAIT_SECONDS = 3

_APPLY_MARKERS = (
    "apply for the job", "відгукнутися на вакансію", "откликнуться на вакансию",
    "відгукнутися", "откликнуться", "apply",
)
_SUBMIT_MARKERS = ("apply for the job", "відгукнутися", "откликнуться", "надіслати", "отправить", "send", "apply")
_APPLIED_MARKERS = (
    "you applied", "you have applied", "ви відгукнулися", "вы откликнулись",
    "відгук надіслано", "application sent",
)


class DjinniProfileRequired(RuntimeError):
    """Профиль кандидата на Djinni не создан — отклики невозможны."""


class DjinniSession:
    def __init__(self, profile_dir: Path):
        self.driver = init_browser(profile_dir)

    def ensure_logged_in(self, parameters: dict) -> None:
        """Вошли — личный кабинет /my/ открывается. Без входа Djinni
        перекидывает на /continue/ (не на /login — подтверждено вживую
        2026-09-25, из-за этого первая проверка ошибочно считала гостя
        вошедшим). Тогда открываем вход с возвратом в кабинет и ждём,
        пока человек войдёт сам (email или Google)."""
        get_with_retry(self.driver, f"{BASE}/my/profile/")
        time.sleep(PAGE_LOAD_WAIT_SECONDS)
        if _in_cabinet(self.driver):
            return
        get_with_retry(self.driver, f"{BASE}/login?lang=en&next=/my/profile/")
        logger.info(f"Djinni: войдите вручную в открывшемся браузере (до {LOGIN_TIMEOUT_SECONDS}с).")
        notify_manual_login_required(parameters, "Djinni", LOGIN_TIMEOUT_SECONDS)
        deadline = time.monotonic() + LOGIN_TIMEOUT_SECONDS
        # После входа через Google Djinni может открыть не кабинет, а любую
        # свою страницу — ждём ухода со страниц входа, потом сверяем кабинет.
        while not _left_login(self.driver):
            if time.monotonic() > deadline:
                raise RuntimeError("Timed out waiting for Djinni login.")
            time.sleep(2)
        get_with_retry(self.driver, f"{BASE}/my/profile/")
        time.sleep(PAGE_LOAD_WAIT_SECONDS)
        if not _in_cabinet(self.driver):
            raise RuntimeError("Djinni: вход не подтвердился — кабинет /my/ не открывается.")

    def quit(self) -> None:
        self.driver.quit()


def _in_cabinet(driver) -> bool:
    """Личный кабинет /my/... открыт — значит, вход выполнен."""
    return "djinni.co/my/" in driver.current_url


def _left_login(driver) -> bool:
    """Вернулись на Djinni и уже не на странице входа/регистрации."""
    url = driver.current_url
    return "djinni.co/" in url and not _guest_redirect(driver)


def _guest_redirect(driver) -> bool:
    """Перекинуло на вход — значит, сессия слетела."""
    return any(p in driver.current_url for p in ("/login", "/continue", "/signup"))


def _visible_by_text(root, markers: tuple[str, ...]):
    """Первая видимая кнопка/ссылка с маркером в тексте — маркеры идут
    от самого точного к общему."""
    candidates = [
        el for el in root.find_elements(By.CSS_SELECTOR, 'button, a, input[type="submit"]')
        if el.is_displayed()
    ]
    for marker in markers:
        for el in candidates:
            text = (el.text or el.get_attribute("value") or "").strip().lower()
            if marker in text:
                return el
    return None


def _already_applied(driver) -> bool:
    text = visible_text(driver).lower()
    return any(m in text for m in _APPLIED_MARKERS)


_UNMET_MARKER = "does not meet some of the requirements"
_UNMET_END = ("if you", "update your profile", "want to compare", "see applicant insights")


def unmet_requirements(driver, job_link: str) -> list[str]:
    """Пустит ли Djinni откликнуться. Пустой список — пустит; иначе строки
    требований, которые профиль не проходит («Only from 7 years of
    experience», «English B2»…) — подтверждено вживую 2026-09-25: Djinni
    прячет кнопку отклика и пишет «Your profile does not meet some of the
    requirements». Проверяем до письма, чтобы не тратить ИИ зря."""
    driver.get(job_link)
    time.sleep(PAGE_LOAD_WAIT_SECONDS)
    raise_if_blocked(visible_text(driver))
    text = visible_text(driver)
    if "can't apply for jobs right now" in text.lower():
        raise DjinniProfileRequired("На Djinni не заполнен профиль кандидата — откликаться нельзя, пока он не создан: djinni.co/my/wizard/")
    start = text.find(_UNMET_MARKER)
    if start < 0:
        return []
    reasons = []
    for line in text[start + len(_UNMET_MARKER):].splitlines():
        line = line.strip()
        if not line or line.lower().startswith("specified by"):
            continue
        if any(line.lower().startswith(e) for e in _UNMET_END) or len(reasons) >= 10:
            break
        reasons.append(line)
    return reasons or ["профиль не проходит требования компании"]


def apply_to_job(driver, job_link: str, message: str) -> bool:
    """True — отклик подтверждённо отправлен (или уже был). False — не
    нашли кнопку/форму, попали на вход или не увидели подтверждения."""
    driver.get(job_link)
    time.sleep(PAGE_LOAD_WAIT_SECONDS)
    raise_if_blocked(visible_text(driver))
    if _guest_redirect(driver):
        return False
    if _already_applied(driver):
        return True
    # Без заполненного профиля Djinni показывает кнопку, но откликнуться не
    # даёт (подтверждено вживую 2026-09-25) — говорим прямо, что делать.
    if "can't apply for jobs right now" in visible_text(driver).lower():
        raise DjinniProfileRequired("На Djinni не заполнен профиль кандидата — откликаться нельзя, пока он не создан: djinni.co/my/wizard/")

    button = _visible_by_text(driver, _APPLY_MARKERS)
    if button is None:
        logger.warning(f"Djinni: не нашёл кнопку отклика на {job_link}")
        return False
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'}); arguments[0].click();", button)
    time.sleep(2)
    if _guest_redirect(driver):
        return False

    fields = [t for t in driver.find_elements(By.TAG_NAME, "textarea") if t.is_displayed()]
    if not fields:
        logger.warning(f"Djinni: после кнопки отклика нет поля для сообщения на {job_link}")
        return False
    field = fields[0]
    field.clear()
    field.send_keys(message)

    # Кнопка отправки — в той же форме, что и поле сообщения.
    forms = field.find_elements(By.XPATH, "./ancestor::form[1]")
    form = forms[0] if forms else driver
    submit = next(
        (b for b in form.find_elements(By.CSS_SELECTOR, 'button[type="submit"], input[type="submit"]') if b.is_displayed()),
        None,
    ) or _visible_by_text(form, _SUBMIT_MARKERS)
    if submit is None:
        logger.warning(f"Djinni: не нашёл кнопку отправки отклика на {job_link}")
        return False
    driver.execute_script("arguments[0].click();", submit)
    time.sleep(3)
    # Подтверждение: сообщение «вы откликнулись» или форма исчезла.
    return _already_applied(driver) or not any(
        t.is_displayed() for t in driver.find_elements(By.TAG_NAME, "textarea")
    )
