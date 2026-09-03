import re
import subprocess
from pathlib import Path
from typing import Optional

import undetected_chromedriver as uc

from src.utils.chrome_utils import (
    clear_profile_cache,
    launch_chrome_with_retry,
)


def _installed_chrome_major_version() -> Optional[int]:
    """Та же логика, что и у init_linkedin_browser: спрашиваем реально
    установленный Chrome напрямую, а не полагаемся на автоопределение
    undetected-chromedriver (подтверждённый живой баг — driver под
    версию новее браузера)."""
    try:
        output = subprocess.check_output(
            [uc.find_chrome_executable(), "--version"],
            timeout=10,
        ).decode()
        match = re.search(r"(\d+)\.", output)
        return int(match.group(1)) if match else None
    except Exception:
        return None


def init_himalayas_browser(profile_dir: Path) -> uc.Chrome:
    """undetected-chromedriver вместо обычного Selenium из
    chrome_utils.init_browser() — подтверждено вживую (2026-09-02):
    /jobs и /companies/... на himalayas.app отдают межстраничную
    проверку "Один момент… Выполнение проверки безопасности" (Cloudflare-
    подобный анти-бот интерстишл) для запроса без реального браузерного
    отпечатка, тогда как главная страница отдаётся сразу — то есть
    защита активна именно на страницах поиска/просмотра вакансий, не на
    сайте в целом. Тот же случай, что и LinkedIn — обычный Selenium
    здесь не подтверждён, undetected-chromedriver обязателен. Постоянная
    папка профиля сохраняет сессию входа между запусками."""
    profile_dir.mkdir(parents=True, exist_ok=True)
    clear_profile_cache(profile_dir)
    version_main = _installed_chrome_major_version()

    def _build() -> uc.Chrome:
        options = uc.ChromeOptions()
        options.add_argument(f"--user-data-dir={profile_dir}")
        options.add_argument("--start-maximized")
        # ponytail: те же флаги, что и у init_linkedin_browser — без
        # них Chrome падает на старте (EXC_BREAKPOINT/SIGTRAP) в связке
        # macOS + постоянный профиль + undetected-chromedriver.
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        return uc.Chrome(options=options, version_main=version_main)

    return launch_chrome_with_retry(_build, profile_dir)
