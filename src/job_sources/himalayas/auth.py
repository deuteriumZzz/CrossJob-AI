import time
from pathlib import Path

from src.job_sources.himalayas.browser import init_himalayas_browser
from src.job_sources.telegram_notify import notify_manual_login_required
from src.logging import logger

LOGIN_URL = "https://himalayas.app/login"
LOGIN_TIMEOUT_SECONDS = 300


class HimalayasSession:
    """Вход — email/пароль (или Google) вводит сам пользователь в
    открывшемся окне браузера, как и LinkedInSession/HabrCareerSession —
    himalayas.app палит автоматизацию не хуже LinkedIn (см. docstring
    init_himalayas_browser: анти-бот интерстишл на /jobs и /companies/...
    подтверждён вживую), автозаполнение полей email/password через
    Selenium здесь так же исключено. Сессия держится через постоянный
    профиль Chrome (profile_dir) — повторный вход не нужен, пока
    himalayas.app сам не сбросит сессию."""

    def __init__(self, profile_dir: Path):
        self.driver = init_himalayas_browser(profile_dir)

    def ensure_logged_in(self, parameters: dict) -> None:
        self.driver.get("https://himalayas.app/")
        time.sleep(3)
        self.driver.get(LOGIN_URL)
        time.sleep(3)
        if "/login" not in self.driver.current_url:
            return

        logger.info(
            "Открылось окно входа himalayas.app — войдите вручную "
            f"(email/пароль или Google) в открывшемся браузере "
            f"(до {LOGIN_TIMEOUT_SECONDS}с)."
        )
        notify_manual_login_required(
            parameters, "Himalayas", LOGIN_TIMEOUT_SECONDS
        )
        deadline = time.monotonic() + LOGIN_TIMEOUT_SECONDS
        while "/login" in self.driver.current_url:
            if time.monotonic() > deadline:
                raise RuntimeError("Timed out waiting for himalayas.app login.")
            time.sleep(2)

    def quit(self) -> None:
        self.driver.quit()
