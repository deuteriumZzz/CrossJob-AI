import time
from pathlib import Path
from typing import Optional

import httpx
from selenium.webdriver.common.by import By

from src.job_sources.block_detection import raise_if_blocked
from src.job_sources.user_agents import random_user_agent
from src.utils.chrome_utils import init_browser

GJ_BASE = "https://geekjob.ru"
PAGE_LOAD_WAIT_SECONDS = 4


class GeekjobClient:
    """Официального API нет — страницы поиска/вакансий geekjob.ru
    отдаются обычным серверным HTML (подтверждено прямым запросом),
    поэтому для чтения достаточно httpx с обычным User-Agent браузера.
    Эндпоинта отклика нет: кнопка "Откликнуться" грузит JS-виджет за
    логином, см. докстринг source.py. user_agent по умолчанию не
    захардкожен — random_user_agent() выбирает один на сессию, чтобы
    не долбить площадку одной и той же строкой годами (см.
    src/job_sources/user_agents.py)."""

    def __init__(self, user_agent: Optional[str] = None):
        self._client = httpx.Client(
            base_url=GJ_BASE,
            headers={"User-Agent": user_agent or random_user_agent()},
            timeout=30,
        )

    def search_vacancies_html(self, query: str, page: int = 1) -> str:
        path = "/vacancies" if page == 1 else f"/vacancies/{page}"
        response = self._client.get(path, params={"q": query})
        response.raise_for_status()
        raise_if_blocked(response)
        return response.text

    def get_vacancy_html(self, vacancy_id: str) -> str:
        response = self._client.get(f"/vacancy/{vacancy_id}")
        response.raise_for_status()
        raise_if_blocked(response)
        return response.text

    def apply(self, vacancy_url: str, profile_dir: Path) -> bool:
        """Best-effort, НЕ проверено на живом аккаунте (в отличие от
        HH/GetMatch): анонимно на странице вакансии подтверждено
        только, что раздел "Откликнуться на вакансию" требует входа
        через OAuth (Google/VK/GitHub и т.д.) — Google-пароль
        пользователя вводить нельзя (см. GeekjobSession), поэтому
        реальную кнопку отправки после входа увидеть было нечем.
        Ищем кнопку с текстом "Откликнуться" внутри самой страницы
        (не якорную ссылку в шапке — та просто прокручивает к разделу)
        — если её там нет, возвращаем False и вызывающий код
        записывает как dry-run, ничего не ломая."""
        driver = init_browser(profile_dir)
        try:
            driver.get(vacancy_url)
            time.sleep(PAGE_LOAD_WAIT_SECONDS)
            page_source = driver.page_source
            raise_if_blocked(page_source)
            buttons = driver.find_elements(
                By.XPATH,
                '//button[contains(normalize-space(), "Откликнуться")]',
            )
            if not buttons:
                return False
            buttons[0].click()
            time.sleep(1)
            return True
        finally:
            driver.quit()
