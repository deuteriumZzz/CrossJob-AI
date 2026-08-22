import time
from pathlib import Path

from selenium.webdriver.common.by import By

from src.logging import logger
from src.utils.chrome_utils import init_browser

RR_BASE = "https://rabota.ru"
LOGIN_TIMEOUT_SECONDS = 300


class RabotaRuSession:
    """Вход у rabota.ru — телефон/email + код, либо OAuth соцсетей
    (ВКонтакте/Mail.Ru/Одноклассники/Яндекс/СберID, проверено вручную
    на живой странице входа). Как и у geekjob.ru — ни один из этих
    способов нельзя пройти автоматически без ввода реальных данных
    пользователя (пароль соцсети или код, пришедший ему лично), что
    здесь никогда не делается — вход целиком ручной, в открывшемся
    окне браузера, тем же способом, что LinkedInSession/
    GeekjobSession ждут ручное завершение входа. Дальше сессия
    держится через постоянный профиль Chrome (profile_dir)."""

    def __init__(self, profile_dir: Path):
        self.profile_dir = profile_dir

    def _is_logged_in(self, driver) -> bool:
        return not driver.find_elements(
            By.XPATH, '//button[normalize-space()="Войти"]'
        )

    def ensure_logged_in(self) -> None:
        driver = init_browser(self.profile_dir)
        try:
            driver.get(RR_BASE)
            time.sleep(3)
            if self._is_logged_in(driver):
                return

            logger.info(
                "Открылось окно входа rabota.ru — войдите вручную "
                "(например через Mail.Ru) в открывшемся браузере "
                f"(до {LOGIN_TIMEOUT_SECONDS}с)."
            )
            deadline = time.monotonic() + LOGIN_TIMEOUT_SECONDS
            while not self._is_logged_in(driver):
                if time.monotonic() > deadline:
                    raise RuntimeError(
                        "Timed out waiting for rabota.ru login."
                    )
                time.sleep(2)
        finally:
            driver.quit()
