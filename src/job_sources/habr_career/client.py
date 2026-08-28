from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import httpx
from selenium.webdriver.common.by import By

from src.job_sources.block_detection import raise_if_blocked, visible_text
from src.job_sources.user_agents import random_user_agent
from src.utils.chrome_utils import init_browser

HC_BASE = "https://career.habr.com"
PAGE_LOAD_WAIT_SECONDS = 3
_APPLY_BUTTON_TEXT = "откликнуться"
_SUBMIT_TEXT_MARKERS = ("отправить", "откликнуться")


class HabrCareerClient:
    """Официального API нет для этого проекта (доступ — по ручному
    одобрению Хабра, не для личных ботов) — /vacancies?q=... и
    /vacancies/{id} отдаются сервером, подтверждено прямым httpx-
    запросом без исполнения JS."""

    def __init__(self, user_agent: Optional[str] = None):
        self._client = httpx.Client(
            base_url=HC_BASE,
            headers={"User-Agent": user_agent or random_user_agent()},
            timeout=30,
        )

    def search_html(self, position: str, page: int = 1) -> str:
        params = {"q": position}
        if page > 1:
            params["page"] = str(page)
        response = self._client.get("/vacancies", params=params)
        response.raise_for_status()
        raise_if_blocked(response)
        return response.text

    def get_vacancy_html(self, vacancy_id: str) -> str:
        response = self._client.get(f"/vacancies/{vacancy_id}")
        response.raise_for_status()
        raise_if_blocked(response)
        return response.text

    def apply(
        self, vacancy_url: str, profile_dir: Path, cover_letter_text: str
    ) -> bool:
        """Best-effort, НЕ проверено на живом залогиненном аккаунте —
        анонимно подтверждено только, что "Откликнуться" на странице
        вакансии — обычный JS-<button> без href (не форма, не якорь).
        Кликаем, ждём модалку, ищем textarea под сопроводительное
        письмо (заполняем, если нашлась — необязательно) и кнопку
        отправки с текстом "отправить"/"откликнуться", отличную от
        первой кнопки, что уже была нажата. Если такой не нашлось —
        считаем сессию/форму неподтверждённой и возвращаем False."""
        driver = init_browser(profile_dir)
        try:
            driver.get(vacancy_url)
            time.sleep(PAGE_LOAD_WAIT_SECONDS)
            raise_if_blocked(visible_text(driver))

            apply_buttons = [
                el
                for el in driver.find_elements(By.CSS_SELECTOR, "button")
                if el.is_displayed()
                and _APPLY_BUTTON_TEXT in (el.text or "").strip().lower()
            ]
            if not apply_buttons:
                return False
            first_button = apply_buttons[0]
            driver.execute_script("arguments[0].click();", first_button)
            time.sleep(2)

            textareas = [
                el
                for el in driver.find_elements(By.CSS_SELECTOR, "textarea")
                if el.is_displayed()
            ]
            if textareas and cover_letter_text:
                textareas[0].send_keys(cover_letter_text)

            submit = _find_submit_button(driver, exclude=first_button)
            if submit is None:
                return False
            driver.execute_script("arguments[0].click();", submit)
            time.sleep(1.5)
            return True
        finally:
            driver.quit()


def _find_submit_button(driver, exclude):
    for el in driver.find_elements(By.CSS_SELECTOR, "button"):
        if not el.is_displayed() or el == exclude:
            continue
        text = (el.text or "").strip().lower()
        if any(marker in text for marker in _SUBMIT_TEXT_MARKERS):
            return el
    return None
