import time
from pathlib import Path

from selenium.webdriver.common.by import By

from src.logging import logger
from src.utils.chrome_utils import init_browser

CR_BASE = "https://careerist.ru"
LOGIN_TIMEOUT_SECONDS = 300


class CareeristSession:
    """Вход у careerist.ru — нет отдельной страницы /login (подтверждено:
    прямой запрос на /user/login/ отдаёт 502 — эта форма грузится только
    во всплывающем окне поверх обычной страницы, через JS
    vfShowInFrame()). Вход/пароль пользователь вводит сам в открывшемся
    браузере, кликнув "Войти" в шапке сайта — как и HeadHunterSession/
    RabotaRuSession, бот здесь никогда не вводит пароль сам. Наличие
    видимой ссылки с классом "loginTop" (подтверждено на живой
    странице) — сигнал, что вход ещё не пройден. Сессия держится через
    постоянный профиль Chrome (profile_dir)."""

    def __init__(self, profile_dir: Path):
        self.profile_dir = profile_dir

    def _is_logged_in(self, driver) -> bool:
        return not driver.find_elements(By.CSS_SELECTOR, "a.loginTop")

    def ensure_logged_in(self) -> None:
        driver = init_browser(self.profile_dir)
        try:
            driver.get(CR_BASE)
            time.sleep(3)
            if self._is_logged_in(driver):
                return

            logger.info(
                "Открылось окно careerist.ru — войдите вручную, нажав "
                '"Войти" в шапке сайта, в открывшемся браузере '
                f"(до {LOGIN_TIMEOUT_SECONDS}с)."
            )
            deadline = time.monotonic() + LOGIN_TIMEOUT_SECONDS
            while not self._is_logged_in(driver):
                if time.monotonic() > deadline:
                    raise RuntimeError(
                        "Timed out waiting for careerist.ru login."
                    )
                time.sleep(2)
        finally:
            driver.quit()
