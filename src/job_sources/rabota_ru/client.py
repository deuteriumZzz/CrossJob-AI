import httpx

RR_BASE = "https://rabota.ru"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


class RabotaRuClient:
    """Официального API нет — страницы поиска/вакансий rabota.ru
    рендерятся сервером с микроразметкой schema.org JobPosting
    (подтверждено прямым запросом), поэтому для чтения достаточно
    httpx с обычным User-Agent браузера. Подтверждённого эндпоинта
    отклика нет, см. source.py."""

    def __init__(self, user_agent: str = DEFAULT_USER_AGENT):
        self._client = httpx.Client(
            base_url=RR_BASE, headers={"User-Agent": user_agent}, timeout=30
        )

    def search_vacancies_html(self, query: str, page: int = 1) -> str:
        response = self._client.get(
            "/vacancy/", params={"query": query, "page": page}
        )
        response.raise_for_status()
        return response.text

    def get_vacancy_html(self, vacancy_id: str) -> str:
        response = self._client.get(f"/vacancy/{vacancy_id}/")
        response.raise_for_status()
        return response.text
