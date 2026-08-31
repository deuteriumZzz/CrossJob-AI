import re
import subprocess
import time
from pathlib import Path
from typing import Optional

import undetected_chromedriver as uc

from src.utils.chrome_utils import clear_profile_cache, clear_stale_chrome_lock

# ponytail: тот же фиксированный retry, что и chrome_utils.init_browser
# — покрывает транзиентные сбои запуска Chrome без диагностики причины.
_RETRY_DELAY_SECONDS = 5


def _installed_chrome_major_version() -> Optional[int]:
    """undetected-chromedriver's own auto-detection иногда подсовывает
    chromedriver под версию новее реально установленного Chrome
    (подтверждено живым запуском: driver под 152, браузер 151.x) —
    достаём версию сами через `--version` и передаём явно как
    version_main, вместо того чтобы полагаться на автоопределение UC."""
    try:
        output = subprocess.check_output(
            [uc.find_chrome_executable(), "--version"],
            timeout=10,
        ).decode()
        match = re.search(r"(\d+)\.", output)
        return int(match.group(1)) if match else None
    except Exception:
        return None


def init_linkedin_browser(profile_dir: Path) -> uc.Chrome:
    """undetected-chromedriver вместо обычного Selenium из
    chrome_utils.init_browser() — LinkedIn активно палит автоматизацию по
    отпечатку браузера, в отличие от остальных площадок проекта.
    Постоянная папка профиля сохраняет сессию входа между запусками."""
    profile_dir.mkdir(parents=True, exist_ok=True)
    clear_profile_cache(profile_dir)
    version_main = _installed_chrome_major_version()
    for attempt in (1, 2):
        clear_stale_chrome_lock(profile_dir)
        options = uc.ChromeOptions()
        options.add_argument(f"--user-data-dir={profile_dir}")
        options.add_argument("--start-maximized")
        # ponytail: без этих двух флагов Chrome падает сразу на старте
        # (EXC_BREAKPOINT/SIGTRAP в CrBrowserMain) именно в связке
        # macOS + постоянный профиль + undetected-chromedriver —
        # известный баг библиотеки (github.com/ultrafunkamsterdam/
        # undetected-chromedriver discussions #1968), не наш профиль
        # и не версия Chrome. chrome_utils.chrome_browser_options()
        # уже ставит их для остальных источников — здесь их не было.
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        try:
            return uc.Chrome(options=options, version_main=version_main)
        except Exception:
            if attempt == 1:
                time.sleep(_RETRY_DELAY_SECONDS)
                continue
            raise
