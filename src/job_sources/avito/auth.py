import time
from pathlib import Path

from selenium.webdriver.common.by import By

from src.job_sources.avito.browser import (
    dismiss_vpn_notice,
    init_avito_browser,
)
from src.job_sources.telegram_notify import notify_manual_login_required
from src.logging import logger
from src.utils.chrome_utils import get_with_retry

AVITO_BASE = "https://www.avito.ru"
LOGIN_TIMEOUT_SECONDS = 300


class AvitoSession:
    """Вход на avito.ru — по номеру телефона + SMS-код (подтверждено
    вживую при публикации резюме), как у HeadHunter — код вводит сам
    пользователь в открывшемся окне браузера, пароль здесь никогда не
    вводится. Сессия держится через постоянный профиль Chrome
    (profile_dir)."""

    def __init__(self, profile_dir: Path):
        self.driver = init_avito_browser(profile_dir)

    def _is_logged_in(self) -> bool:
        return not self.driver.find_elements(
            By.XPATH, '//a[contains(@href, "#login")]'
        )

    def warm_up(self) -> None:
        """Заход на главную перед первым запросом к поиску — реальный
        прогон 2026-09-29 показал блокировку ("Доступ ограничен") при
        первом же запросе прямо на /all/vakansii?q=... с чистого
        профиля без предварительного визита на главную (в отличие от
        Himalayas/HH, где ensure_logged_in всегда заходит на главную
        первой). Не ждёт входа — только даёт антибот-системе увидеть
        обычную навигацию, а не прыжок сразу на глубокий URL.

        Плашка "Продолжить" (VPN/другая страна) не добивается
        события "load" целиком — подтверждено вживую 2026-09-29,
        driver.get() зависал на read-timeout вместо TimeoutException
        (см. set_page_load_timeout в init_avito_browser). Ошибку
        здесь не пробрасываем — если страница всё же не открылась,
        просто пробуем кликнуть плашку по тому, что успело
        отрендериться, а поиск сам поймает настоящую блокировку через
        raise_if_blocked."""
        try:
            get_with_retry(self.driver, AVITO_BASE)
        except Exception as e:
            logger.warning(f"avito.ru warm-up navigation failed: {e}")
        time.sleep(3)
        dismiss_vpn_notice(self.driver)

    def ensure_logged_in(self, parameters: dict) -> None:
        self.warm_up()
        if self._is_logged_in():
            return

        logger.info(
            "Открылось окно входа avito.ru — войдите вручную (телефон + "
            f"SMS-код) в открывшемся браузере (до {LOGIN_TIMEOUT_SECONDS}с)."
        )
        notify_manual_login_required(
            parameters, "avito.ru", LOGIN_TIMEOUT_SECONDS
        )
        deadline = time.monotonic() + LOGIN_TIMEOUT_SECONDS
        while not self._is_logged_in():
            if time.monotonic() > deadline:
                raise RuntimeError("Timed out waiting for avito.ru login.")
            time.sleep(2)

    def quit(self) -> None:
        self.driver.quit()
