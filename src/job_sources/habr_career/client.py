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
_ALREADY_APPLIED_MARKERS = ("посмотреть отклик", "редактировать")


class HabrCareerClient:
    """Официального API нет для этого проекта (доступ — по ручному
    одобрению Хабра, не для личных ботов) — /vacancies?q=... и
    /vacancies/{id} отдаются сервером, подтверждено прямым httpx-
    запросом без исполнения JS — поиск здесь всегда идёт через httpx,
    браузер нужен только для apply().

    ponytail: используйте как контекстный менеджер (`with
    HabrCareerClient(profile_dir) as client:`), чтобы один Chrome
    переиспользовался на все отклики за прогон (тот же паттерн, что
    у HeadHunterBrowserClient — тоже раньше открывал/закрывал браузер
    на каждый вызов, есть жалоба пользователя на это же поведение).
    Без `with` — свой одноразовый driver на вызов apply()."""

    def __init__(
        self,
        profile_dir: Optional[Path] = None,
        user_agent: Optional[str] = None,
    ):
        self.profile_dir = profile_dir
        self._driver = None
        self._client = httpx.Client(
            base_url=HC_BASE,
            headers={"User-Agent": user_agent or random_user_agent()},
            timeout=30,
        )

    def __enter__(self) -> "HabrCareerClient":
        if self.profile_dir is not None:
            self._driver = init_browser(self.profile_dir)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._driver is not None:
            self._driver.quit()
            self._driver = None

    def _acquire_driver(self):
        if self._driver is not None:
            return self._driver, False
        if self.profile_dir is None:
            raise RuntimeError(
                "HabrCareerClient.apply() needs profile_dir (constructor "
                "arg or __enter__)."
            )
        return init_browser(self.profile_dir), True

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

    def apply(self, vacancy_url: str) -> bool:
        """Подтверждено на живом залогиненном аккаунте (2026-08-28):
        для вошедшего пользователя "Откликнуться" — мгновенная
        отправка ОДНИМ кликом, без модалки, без поля под письмо, без
        кнопки подтверждения (сопроводительное письмо сюда прикрепить
        нельзя — ponytail: если понадобится, у Хабра есть отдельное
        "Дополнить отклик" уже ПОСЛЕ отправки, не реализовано).
        Анонимная форма ("Откликнуться без регистрации") — под
        reCAPTCHA, которую бот не проходит принципиально, поэтому сюда
        не заходим вообще: если после клика не появились маркеры уже
        отправленного отклика ("Посмотреть отклик"/"Редактировать") —
        считаем, что сессия не аутентифицирована (сработала анонимная
        ветка с капчей или что-то ещё), и возвращаем False, ничего
        больше не нажимая."""
        driver, owns_it = self._acquire_driver()
        try:
            driver.get(vacancy_url)
            time.sleep(PAGE_LOAD_WAIT_SECONDS)
            raise_if_blocked(visible_text(driver))

            apply_buttons = [
                el
                for el in driver.find_elements(By.CSS_SELECTOR, "button")
                if el.is_displayed()
                and (el.text or "").strip().lower() == _APPLY_BUTTON_TEXT
            ]
            if not apply_buttons:
                return False
            driver.execute_script("arguments[0].click();", apply_buttons[0])
            time.sleep(2)

            texts = [
                (el.text or "").strip().lower()
                for el in driver.find_elements(By.CSS_SELECTOR, "button, a")
                if el.is_displayed()
            ]
            return any(
                marker in text
                for text in texts
                for marker in _ALREADY_APPLIED_MARKERS
            )
        finally:
            if owns_it:
                driver.quit()
