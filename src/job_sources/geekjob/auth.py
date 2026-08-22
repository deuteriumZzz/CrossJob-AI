import time
from pathlib import Path

from selenium.webdriver.common.by import By

from src.logging import logger
from src.utils.chrome_utils import init_browser

GJ_BASE = "https://geekjob.ru"
LOGIN_TIMEOUT_SECONDS = 300


class GeekjobSession:
    """geekjob.ru не даёт войти по коду/паролю напрямую — только через
    OAuth соцсетей (Google/VK/GitHub/Yandex и т.д., проверено вручную
    на живой странице входа). Ни один из этих провайдеров нельзя
    пройти автоматически без ввода реального пароля пользователя, что
    здесь никогда не делается — вход целиком ручной, в открывшемся
    окне браузера, так же, как LinkedInSession ждёт ручное
    прохождение 2FA. Дальше сессия держится через постоянный профиль
    Chrome (profile_dir)."""

    def __init__(self, profile_dir: Path):
        self.profile_dir = profile_dir

    def _is_logged_in(self, driver) -> bool:
        return not driver.find_elements(
            By.XPATH, '//a[normalize-space()="Войти / Регистрация"]'
        )

    def ensure_logged_in(self) -> None:
        driver = init_browser(self.profile_dir)
        try:
            driver.get(GJ_BASE)
            time.sleep(3)
            if self._is_logged_in(driver):
                return

            logger.info(
                "Открылось окно входа geekjob.ru — войдите вручную "
                "(например через Google) в открывшемся браузере "
                f"(до {LOGIN_TIMEOUT_SECONDS}с)."
            )
            deadline = time.monotonic() + LOGIN_TIMEOUT_SECONDS
            while not self._is_logged_in(driver):
                if time.monotonic() > deadline:
                    raise RuntimeError(
                        "Timed out waiting for geekjob.ru login."
                    )
                time.sleep(2)
        finally:
            driver.quit()
