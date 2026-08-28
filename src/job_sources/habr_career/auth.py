import time
from pathlib import Path

from selenium.webdriver.common.by import By

from src.logging import logger
from src.utils.chrome_utils import init_browser

HC_BASE = "https://career.habr.com"
LOGIN_TIMEOUT_SECONDS = 300


class HabrCareerSession:
    """Вход у career.habr.com — единый аккаунт Хабра через OAuth-редирект
    /users/auth/tmid ("Войти через Хабр Аккаунт"), подтверждено прямым
    запросом (2026-08-28) — отдельной простой формы логина нет. Вход/
    пароль пользователь вводит сам в открывшемся браузере — как и
    GeekjobSession/RabotaRuSession, бот здесь никогда не вводит пароль
    сам. Наличие видимого элемента с классом "js-data-sign-in-btn"
    (подтверждено на живой странице) — сигнал, что вход ещё не пройден.
    Сессия держится через постоянный профиль Chrome (profile_dir)."""

    def __init__(self, profile_dir: Path):
        self.profile_dir = profile_dir

    def _is_logged_in(self, driver) -> bool:
        return not driver.find_elements(
            By.CSS_SELECTOR, "a.js-data-sign-in-btn"
        )

    def ensure_logged_in(self) -> None:
        driver = init_browser(self.profile_dir)
        try:
            driver.get(HC_BASE)
            time.sleep(3)
            if self._is_logged_in(driver):
                return

            logger.info(
                "Открылось окно career.habr.com — войдите вручную "
                '(кнопка "Войти" → "Войти через Хабр Аккаунт") в '
                f"открывшемся браузере (до {LOGIN_TIMEOUT_SECONDS}с)."
            )
            deadline = time.monotonic() + LOGIN_TIMEOUT_SECONDS
            while not self._is_logged_in(driver):
                if time.monotonic() > deadline:
                    raise RuntimeError(
                        "Timed out waiting for career.habr.com login."
                    )
                time.sleep(2)
        finally:
            driver.quit()
