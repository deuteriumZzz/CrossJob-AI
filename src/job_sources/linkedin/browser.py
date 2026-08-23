import re
import subprocess
from pathlib import Path
from typing import Optional

import undetected_chromedriver as uc


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
    options = uc.ChromeOptions()
    options.add_argument(f"--user-data-dir={profile_dir}")
    options.add_argument("--start-maximized")
    return uc.Chrome(
        options=options, version_main=_installed_chrome_major_version()
    )
