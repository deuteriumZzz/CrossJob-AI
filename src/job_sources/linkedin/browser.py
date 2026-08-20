from pathlib import Path

import undetected_chromedriver as uc


def init_linkedin_browser(profile_dir: Path) -> uc.Chrome:
    """undetected-chromedriver вместо обычного Selenium из
    chrome_utils.init_browser() — LinkedIn активно палит автоматизацию по
    отпечатку браузера, в отличие от остальных площадок проекта.
    Постоянная папка профиля сохраняет сессию входа между запусками."""
    profile_dir.mkdir(parents=True, exist_ok=True)
    options = uc.ChromeOptions()
    options.add_argument(f"--user-data-dir={profile_dir}")
    options.add_argument("--start-maximized")
    return uc.Chrome(options=options)
