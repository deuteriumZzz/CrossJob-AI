import time
from pathlib import Path

from src.job_sources.linkedin.browser import init_linkedin_browser
from src.logging import logger

LOGIN_URL = "https://www.linkedin.com/login"
LOGIN_TIMEOUT_SECONDS = 300


class LinkedInSession:
    """Вход — email/пароль (и любую 2FA-проверку) вводит сам
    пользователь в открывшемся окне браузера, как и HeadHunterSession/
    GetMatchSession/RabotaRuSession — LinkedIn палит автоматизацию
    агрессивнее остальных площадок проекта, и автозаполнение формы
    логина через Selenium (send_keys в поля username/password) —
    ровно тот паттерн, который детектится в первую очередь; раньше
    здесь так и было сделано, из-за чего HeadHunterSession уже был
    написан "как и LinkedInSession" — сверяем реальность с этим
    докстрингом. Сессия держится через постоянный профиль Chrome
    (profile_dir) — повторный вход не нужен, пока LinkedIn сам не
    сбросит сессию."""

    def __init__(self, profile_dir: Path):
        self.driver = init_linkedin_browser(profile_dir)

    def ensure_logged_in(self) -> None:
        self.driver.get("https://www.linkedin.com/feed/")
        time.sleep(3)
        if "/feed" in self.driver.current_url:
            return

        self.driver.get(LOGIN_URL)
        logger.info(
            "Открылось окно входа LinkedIn — войдите вручную (email, "
            "пароль, любая 2FA-проверка) в открывшемся браузере "
            f"(до {LOGIN_TIMEOUT_SECONDS}с)."
        )
        deadline = time.monotonic() + LOGIN_TIMEOUT_SECONDS
        while "/feed" not in self.driver.current_url:
            if time.monotonic() > deadline:
                raise RuntimeError("Timed out waiting for LinkedIn login.")
            time.sleep(2)

    def quit(self) -> None:
        self.driver.quit()
