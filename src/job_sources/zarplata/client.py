import httpx

# ponytail: подтверждено (в списке permitted-hosts github.com/hhru/api
# рядом с hh.ru есть zarplata.ru/api.zarplata.ru), что zarplata.ru
# работает на той же платформе HeadHunter-Group, что и hh.ru, но именно
# этот базовый URL и форма эндпоинтов выведены по аналогии с общей
# платформой, а не проверены боевым вызовом (в отличие от api.hh.ru).
# Проверить при первом запуске.
ZP_API_BASE = "https://api.zarplata.ru"
DEFAULT_USER_AGENT = "CrossJob-AI/1.0"


class ZarplataClient:
    def __init__(
        self, access_token: str, user_agent: str = DEFAULT_USER_AGENT
    ):
        self._client = httpx.Client(
            base_url=ZP_API_BASE,
            headers={
                "Authorization": f"Bearer {access_token}",
                "User-Agent": user_agent,
            },
            timeout=30,
        )

    def search_vacancies(self, params: dict) -> dict:
        response = self._client.get("/vacancies", params=params)
        response.raise_for_status()
        return response.json()

    def get_vacancy(self, vacancy_id: str) -> dict:
        response = self._client.get(f"/vacancies/{vacancy_id}")
        response.raise_for_status()
        return response.json()

    def get_employer(self, employer_id: str) -> dict:
        response = self._client.get(f"/employers/{employer_id}")
        response.raise_for_status()
        return response.json()

    def list_negotiations(self) -> list[dict]:
        response = self._client.get("/negotiations")
        response.raise_for_status()
        return response.json()["items"]

    def apply(self, vacancy_id: str, resume_id: str, message: str) -> None:
        response = self._client.post(
            "/negotiations",
            data={
                "vacancy_id": vacancy_id,
                "resume_id": resume_id,
                "message": message,
            },
        )
        response.raise_for_status()
