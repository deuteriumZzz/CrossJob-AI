import re
import subprocess
from pathlib import Path
from typing import Optional

import undetected_chromedriver as uc

from src.utils.chrome_utils import clear_profile_cache, launch_chrome_with_retry


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
    Постоянная папка профиля сохраняет сессию входа между запусками.

    ponytail: пробовали закрепить версию отдельным скачанным билдом
    Chrome for Testing вместо обычного установленного Chrome, чтобы
    убрать дрейф версии (система обновляет обычный Chrome сама, он
    убегает вперёд запатченного chromedriver — github.com/
    ultrafunkamsterdam/undetected-chromedriver discussions #1968).
    Откатили 2026-09-01: этот билд без подписи Apple, macOS на каждый
    запуск спрашивает пароль/разрешение — для демона без присмотра это
    хуже редкого дрейфа версии. Обычный Chrome подписан и нотаризован
    Apple, так что диалогов не просит."""
    profile_dir.mkdir(parents=True, exist_ok=True)
    clear_profile_cache(profile_dir)
    version_main = _installed_chrome_major_version()

    def _build() -> uc.Chrome:
        options = uc.ChromeOptions()
        options.add_argument(f"--user-data-dir={profile_dir}")
        options.add_argument("--start-maximized")
        # ponytail: без этих флагов Chrome падает сразу на старте
        # (EXC_BREAKPOINT/SIGTRAP в CrBrowserMain) в связке macOS +
        # постоянный профиль + undetected-chromedriver — известный баг
        # библиотеки (discussions #1968/#2253). chrome_utils.
        # chrome_browser_options() уже ставит их для остальных
        # источников — здесь их не было.
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        return uc.Chrome(options=options, version_main=version_main)

    return launch_chrome_with_retry(_build, profile_dir)
