import httpx

SJ_API_BASE = "https://api.superjob.ru/2.0"
DEFAULT_USER_AGENT = "CrossJob-AI/1.0"


class SuperJobClient:
    """Эндпоинты проверены по исходникам официального PHP-клиента
    (github.com/superjobru/superjob-api-client, SuperjobAPI.php)."""

    def __init__(
        self,
        access_token: str,
        client_secret: str,
        user_agent: str = DEFAULT_USER_AGENT,
    ):
        self._client = httpx.Client(
            base_url=SJ_API_BASE,
            headers={
                "Authorization": f"Bearer {access_token}",
                "X-Api-App-Id": client_secret,
                "User-Agent": user_agent,
            },
            timeout=30,
        )

    def search_vacancies(self, params: dict) -> dict:
        response = self._client.get("/vacancies/", params=params)
        response.raise_for_status()
        return response.json()

    def get_vacancy(self, vacancy_id: str) -> dict:
        response = self._client.get(f"/vacancies/{vacancy_id}/")
        response.raise_for_status()
        return response.json()

    def get_employer(self, client_id: str) -> dict:
        response = self._client.get(f"/clients/{client_id}/")
        response.raise_for_status()
        return response.json()

    def list_resumes(self) -> list[dict]:
        """GET /resumes/ — метод resumes() официального PHP-клиента.
        Как и list_messages() — путь подтверждён по исходникам, но
        не проверен боевым вызовом на живом аккаунте."""
        response = self._client.get("/resumes/")
        response.raise_for_status()
        return response.json().get("objects", [])

    def list_messages(self) -> list[dict]:
        """GET /messages/ — путь эндпоинта подтверждён методом
        messages() официального PHP-клиента, но точные названия полей
        ответа (какой вакансии касается сообщение, его статус) не
        проверены боевым вызовом, в отличие от search/apply выше."""
        response = self._client.get("/messages/")
        response.raise_for_status()
        return response.json().get("objects", [])

    def apply(self, resume_id: str, vacancy_id: str, comment: str) -> None:
        response = self._client.post(
            "/send_cv_on_vacancy/",
            data={
                "id_cv": resume_id,
                "id_vacancy": vacancy_id,
                "comment": comment,
            },
        )
        response.raise_for_status()
