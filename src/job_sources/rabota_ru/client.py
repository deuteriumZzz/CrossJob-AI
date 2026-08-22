import time
from pathlib import Path
from typing import Optional

import httpx
from selenium.webdriver.common.by import By

from src.job_sources.block_detection import raise_if_blocked, visible_text
from src.job_sources.user_agents import random_user_agent
from src.utils.chrome_utils import init_browser

RR_BASE = "https://rabota.ru"
PAGE_LOAD_WAIT_SECONDS = 4


class RabotaRuClient:
    """Официального API нет — страницы поиска/вакансий rabota.ru
    рендерятся сервером с микроразметкой schema.org JobPosting
    (подтверждено прямым запросом), поэтому для чтения достаточно
    httpx с обычным User-Agent браузера. Подтверждённого эндпоинта
    отклика нет, см. source.py. user_agent по умолчанию не
    захардкожен — random_user_agent() выбирает один на сессию (см.
    src/job_sources/user_agents.py)."""

    def __init__(self, user_agent: Optional[str] = None):
        self._client = httpx.Client(
            base_url=RR_BASE,
            headers={"User-Agent": user_agent or random_user_agent()},
            timeout=30,
        )

    def search_vacancies_html(self, query: str, page: int = 1) -> str:
        response = self._client.get(
            "/vacancy/", params={"query": query, "page": page}
        )
        response.raise_for_status()
        raise_if_blocked(response)
        return response.text

    def get_vacancy_html(self, vacancy_id: str) -> str:
        response = self._client.get(f"/vacancy/{vacancy_id}/")
        response.raise_for_status()
        raise_if_blocked(response)
        return response.text

    def apply(self, vacancy_url: str, profile_dir: Path) -> bool:
        """Best-effort, НЕ проверено на живом залогиненном аккаунте —
        только подтверждено анонимно, что на странице вакансии есть
        <button>Откликнуться</button> (см. RabotaRuSession — вход у
        rabota.ru тоже только через OAuth/код, пароль пользователя
        здесь не вводится). Если кнопки нет — возвращаем False,
        вызывающий код запишет как dry-run, без падения."""
        driver = init_browser(profile_dir)
        try:
            driver.get(vacancy_url)
            time.sleep(PAGE_LOAD_WAIT_SECONDS)
            raise_if_blocked(visible_text(driver))
            buttons = driver.find_elements(
                By.XPATH, '//button[normalize-space()="Откликнуться"]'
            )
            if not buttons:
                return False
            buttons[0].click()
            time.sleep(1)
            return True
        finally:
            driver.quit()
