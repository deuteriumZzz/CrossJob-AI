import httpx

GJ_BASE = "https://geekjob.ru"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


class GeekjobClient:
    """Официального API нет — страницы поиска/вакансий geekjob.ru
    отдаются обычным серверным HTML (подтверждено прямым запросом),
    поэтому для чтения достаточно httpx с обычным User-Agent браузера.
    Эндпоинта отклика нет: кнопка "Откликнуться" грузит JS-виджет за
    логином, см. докстринг source.py."""

    def __init__(self, user_agent: str = DEFAULT_USER_AGENT):
        self._client = httpx.Client(
            base_url=GJ_BASE, headers={"User-Agent": user_agent}, timeout=30
        )

    def search_vacancies_html(self, query: str, page: int = 1) -> str:
        path = "/vacancies" if page == 1 else f"/vacancies/{page}"
        response = self._client.get(path, params={"q": query})
        response.raise_for_status()
        return response.text

    def get_vacancy_html(self, vacancy_id: str) -> str:
        response = self._client.get(f"/vacancy/{vacancy_id}")
        response.raise_for_status()
        return response.text
