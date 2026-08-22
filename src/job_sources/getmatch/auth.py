import time
from pathlib import Path

from selenium.webdriver.common.by import By

from src.logging import logger
from src.utils.chrome_utils import init_browser

GM_BASE = "https://getmatch.ru"
LOGIN_TIMEOUT_SECONDS = 300


class GetMatchSession:
    """Вход у GetMatch — не пароль, а код, присланный в Telegram
    (проверено вручную на живом аккаунте): вводим только email/
    телеграм, дальше код вводит сам пользователь в открывшемся окне
    браузера — тем же способом, что LinkedInSession ждёт ручное
    прохождение 2FA. Сессия дальше держится через постоянный профиль
    Chrome (profile_dir), повторный вход не нужен, пока GetMatch сам
    не сбросит сессию."""

    def __init__(self, profile_dir: Path):
        self.profile_dir = profile_dir

    def _is_logged_in(self, driver) -> bool:
        return not driver.find_elements(
            By.XPATH, '//button[normalize-space()="Войти"]'
        )

    def ensure_logged_in(self, email: str) -> None:
        driver = init_browser(self.profile_dir)
        try:
            driver.get(f"{GM_BASE}/profile")
            time.sleep(4)
            if self._is_logged_in(driver):
                return

            driver.get(GM_BASE)
            time.sleep(3)
            driver.find_element(
                By.XPATH, '//button[normalize-space()="Войти"]'
            ).click()
            time.sleep(1)
            driver.find_element(
                By.CSS_SELECTOR, 'input[placeholder="Почта или телеграм"]'
            ).send_keys(email)
            driver.find_element(
                By.CSS_SELECTOR, 'button[type="submit"]'
            ).click()

            logger.info(
                "Открылось окно входа GetMatch — введите код, "
                "присланный в Telegram, вручную в открывшемся браузере "
                f"(до {LOGIN_TIMEOUT_SECONDS}с)."
            )
            deadline = time.monotonic() + LOGIN_TIMEOUT_SECONDS
            while not self._is_logged_in(driver):
                if time.monotonic() > deadline:
                    raise RuntimeError("Timed out waiting for GetMatch login.")
                time.sleep(2)
        finally:
            driver.quit()
