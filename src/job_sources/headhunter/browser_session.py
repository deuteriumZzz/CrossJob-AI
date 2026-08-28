import time
from pathlib import Path

from selenium.webdriver.common.by import By

from src.logging import logger
from src.utils.chrome_utils import init_browser

HH_BASE = "https://hh.ru"
LOGIN_TIMEOUT_SECONDS = 300
_LOGGED_IN_MARKER = '[data-qa="mainmenu_profileAndResumes"]'


class HeadHunterSession:
    """Вход у hh.ru — номер телефона + код из SMS (подтверждено прямым
    просмотром живого аккаунта: официальный OAuth API требует
    регистрации отдельного приложения, которое HH одобряет не сразу и
    не гарантированно — это не подходит, см. HHAuth/HeadHunterClient в
    auth.py/client.py, оставленные как более старая OAuth-реализация). Как и
    LinkedInSession/GetMatchSession/RabotaRuSession, вход целиком
    ручной в открывшемся окне браузера: номер телефона и код из SMS
    вводит сам пользователь, автоматизация только ждёт. Дальше сессия
    держится через постоянный профиль Chrome (profile_dir) — повторный
    вход не нужен, пока hh.ru сам не сбросит сессию."""

    def __init__(self, profile_dir: Path):
        self.profile_dir = profile_dir

    def _is_logged_in(self, driver) -> bool:
        return bool(driver.find_elements(By.CSS_SELECTOR, _LOGGED_IN_MARKER))

    def ensure_logged_in(self) -> None:
        driver = init_browser(self.profile_dir)
        try:
            driver.get(HH_BASE)
            time.sleep(3)
            if self._is_logged_in(driver):
                return

            logger.info(
                "Открылось окно входа hh.ru — войдите вручную по номеру "
                "телефона (придёт SMS-код) в открывшемся браузере "
                f"(до {LOGIN_TIMEOUT_SECONDS}с)."
            )
            deadline = time.monotonic() + LOGIN_TIMEOUT_SECONDS
            while not self._is_logged_in(driver):
                if time.monotonic() > deadline:
                    raise RuntimeError("Timed out waiting for hh.ru login.")
                time.sleep(2)
        finally:
            driver.quit()
