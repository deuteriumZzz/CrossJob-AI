import re
import subprocess
import time
from pathlib import Path
from typing import Optional

import undetected_chromedriver as uc
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.by import By

from src.utils.chrome_utils import (
    clear_profile_cache,
    launch_chrome_with_retry,
)
from src.utils.shared_browser import hide_extra_window


def _installed_chrome_major_version() -> Optional[int]:
    try:
        output = subprocess.check_output(
            [uc.find_chrome_executable(), "--version"],
            timeout=10,
        ).decode()
        match = re.search(r"(\d+)\.", output)
        return int(match.group(1)) if match else None
    except Exception:
        return None


def init_avito_browser(profile_dir: Path) -> uc.Chrome:
    """undetected-chromedriver вместо обычного Selenium — подтверждено
    вживую (2026-09-29): страница вакансии avito.ru отдала "Доступ
    ограничен: проверка безопасности" на запрос без реального
    браузерного отпечатка, тогда как страница поиска (/all/vakansii)
    отдаётся анонимно без проблем. Тот же случай, что у LinkedIn/
    Himalayas — обычный Selenium здесь не подтверждён."""
    profile_dir.mkdir(parents=True, exist_ok=True)
    clear_profile_cache(profile_dir)
    version_main = _installed_chrome_major_version()

    def _build() -> uc.Chrome:
        options = uc.ChromeOptions()
        options.add_argument(f"--user-data-dir={profile_dir}")
        options.add_argument("--start-maximized")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        # ponytail: страница с плашкой "Продолжить" (VPN/другая
        # страна) никогда не добивается события "load" целиком —
        # подтверждено вживую 2026-09-29, driver.get() висел на
        # read-timeout (120с) на каждой попытке. "eager" отдаёт
        # управление сразу после разбора DOM, не дожидаясь фоновых
        # запросов/пикселей — dismiss_vpn_notice успевает кликнуть.
        options.page_load_strategy = "eager"
        driver = uc.Chrome(options=options, version_main=version_main)
        driver.set_page_load_timeout(30)
        return driver

    return hide_extra_window(launch_chrome_with_retry(_build, profile_dir))


def dismiss_vpn_notice(driver) -> None:
    """avito.ru показывает промежуточную страницу с кнопкой
    "Продолжить" при заходе через VPN/из другой страны (подтверждено
    пользователем вживую 2026-09-29) — это не капча/бан, страница
    пропускает после одного клика. Вызывается перед raise_if_blocked,
    чтобы не принять эту страницу за настоящую блокировку.

    React-страница может переотрисовать DOM между find_elements и
    is_displayed/click на каком-то из элементов — подтверждено вживую
    2026-09-29 (StaleElementReferenceException на первой же реальной
    позиции), поэтому такой элемент просто пропускается вместо падения
    всего поиска по этой позиции."""
    for el in driver.find_elements(By.XPATH, "//button|//a"):
        try:
            if not el.is_displayed():
                continue
            if (el.text or "").strip().lower() == "продолжить":
                driver.execute_script("arguments[0].click();", el)
                time.sleep(2)
                return
        except StaleElementReferenceException:
            continue
