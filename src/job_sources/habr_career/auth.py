import time
from pathlib import Path

from selenium.webdriver.common.by import By

from src.logging import logger
from src.utils.chrome_utils import init_browser

HC_BASE = "https://career.habr.com"
LOGIN_TIMEOUT_SECONDS = 300


class HabrCareerSession:
    """Вход у career.habr.com — единый аккаунт Хабра через OAuth-редирект
    /users/auth/tmid ("Войти через Хабр Аккаунт", включая вход через
    Google) — отдельной простой формы логина нет. Вход/пароль
    пользователь вводит сам в открывшемся браузере — как и
    GeekjobSession/RabotaRuSession, бот здесь никогда не вводит пароль
    сам.

    ponytail: раньше проверка входа смотрела на ОТСУТСТВИЕ кнопки
    "Войти" — ложно срабатывала во время OAuth-редиректа на
    accounts.google.com (там кнопки "Войти" тоже нет, потому что это
    вообще не страница Хабра), из-за чего бот выдёргивал браузер на
    другую страницу посреди входа пользователя через Google (баг
    найден вживую 2026-08-28). Теперь — обратный, положительный сигнал:
    ссылка на /profile/notifications есть в шапке только у вошедшего
    пользователя (подтверждено на живом залогиненном аккаунте)."""

    def __init__(self, profile_dir: Path):
        self.profile_dir = profile_dir

    def _is_logged_in(self, driver) -> bool:
        return bool(
            driver.find_elements(
                By.CSS_SELECTOR, 'a[href$="/profile/notifications"]'
            )
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
