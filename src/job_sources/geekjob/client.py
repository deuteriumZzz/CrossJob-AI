from typing import Optional

import httpx

from src.job_sources.block_detection import raise_if_blocked
from src.job_sources.user_agents import random_user_agent

GJ_BASE = "https://geekjob.ru"


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
