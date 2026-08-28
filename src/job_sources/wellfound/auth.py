import time
from pathlib import Path

from src.logging import logger
from src.utils.chrome_utils import init_browser

WF_BASE = "https://wellfound.com"
LOGIN_TIMEOUT_SECONDS = 300


class WellfoundSession:
    """Вход у wellfound.com не подтверждён на живом залогиненном
    аккаунте — форма "Apply Now" для анонимного пользователя требует
    прямо в модалке завести аккаунт (имя, email, свой пароль), а не
    просто войти (см. client.py). Пароль от аккаунта пользователь
    всегда придумывает и вводит сам в открывшемся окне — как и
    HeadHunterSession/RabotaRuSession/LinkedInSession, здесь НИКОГДА
    не создаётся аккаунт и не подставляется пароль в коде. Логиненную
    страницу /login wellfound.com уводит на другой URL — это и есть
    сигнал успешного входа, кнопку/элемент никто не подтверждал.
    Сессия держится через постоянный профиль Chrome (profile_dir)."""

    def __init__(self, profile_dir: Path):
        self.profile_dir = profile_dir

    def ensure_logged_in(self) -> None:
        driver = init_browser(self.profile_dir)
        try:
            driver.get(f"{WF_BASE}/login")
            time.sleep(3)
            if "/login" not in driver.current_url:
                return

            logger.info(
                "Открылось окно входа wellfound.com — войдите или "
                "создайте аккаунт вручную (email, свой пароль) в "
                f"открывшемся браузере (до {LOGIN_TIMEOUT_SECONDS}с). "
                "Пароль всегда придумывает и вводит сам пользователь — "
                "бот его никогда не создаёт и не хранит."
            )
            deadline = time.monotonic() + LOGIN_TIMEOUT_SECONDS
            while "/login" in driver.current_url:
                if time.monotonic() > deadline:
                    raise RuntimeError(
                        "Timed out waiting for wellfound.com login."
                    )
                time.sleep(2)
        finally:
            driver.quit()
