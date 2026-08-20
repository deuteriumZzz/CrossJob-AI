from typing import Optional

import httpx

from src.job_sources.block_detection import raise_if_blocked
from src.job_sources.user_agents import random_user_agent

RR_BASE = "https://rabota.ru"


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
