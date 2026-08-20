import time
from pathlib import Path

from selenium.webdriver.common.by import By

from src.job_sources.linkedin.browser import init_linkedin_browser
from src.logging import logger

LOGIN_URL = "https://www.linkedin.com/login"
LOGIN_TIMEOUT_SECONDS = 300


class LinkedInSession:
    """Вход сохраняется через профильную папку браузера (browser.py) —
    здесь заполняется сама форма логина только при первом запуске или
    когда LinkedIn сбрасывает сессию."""

    def __init__(self, profile_dir: Path):
        self.driver = init_linkedin_browser(profile_dir)

    def ensure_logged_in(self, email: str, password: str) -> None:
        self.driver.get("https://www.linkedin.com/feed/")
        time.sleep(3)
        if "/feed" in self.driver.current_url:
            return

        self.driver.get(LOGIN_URL)
        time.sleep(2)
        self.driver.find_element(By.ID, "username").send_keys(email)
        self.driver.find_element(By.ID, "password").send_keys(password)
        self.driver.find_element(
            By.CSS_SELECTOR, "button[type='submit']"
        ).click()

        logger.info(
            "Waiting for LinkedIn login (finish any 2FA/verification "
            "in the browser window)..."
        )
        deadline = time.monotonic() + LOGIN_TIMEOUT_SECONDS
        while "/feed" not in self.driver.current_url:
            if time.monotonic() > deadline:
                raise RuntimeError("Timed out waiting for LinkedIn login.")
            time.sleep(2)

    def quit(self) -> None:
        self.driver.quit()
