import httpx

HH_API_BASE = "https://api.hh.ru"
DEFAULT_USER_AGENT = "CrossJob-AI/1.0"


class HeadHunterClient:
    def __init__(
        self, access_token: str, user_agent: str = DEFAULT_USER_AGENT
    ):
        self._client = httpx.Client(
            base_url=HH_API_BASE,
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

    def list_resumes(self) -> list[dict]:
        response = self._client.get("/resumes/mine")
        response.raise_for_status()
        return response.json()["items"]

    def list_negotiations(self) -> list[dict]:
        response = self._client.get("/negotiations")
        response.raise_for_status()
        return response.json()["items"]

    def get_resume(self, resume_id: str) -> dict:
        """Полный текст резюме на hh.ru (не список из list_resumes(),
        а конкретное резюме по ID) — источник структурированных
        данных (зарплата, навыки) для автоответов на сообщения
        работодателя."""
        response = self._client.get(f"/resumes/{resume_id}")
        response.raise_for_status()
        return response.json()

    def list_negotiation_messages(self, negotiation_id: str) -> list[dict]:
        """НЕ проверено вызовом на живом аккаунте — поля по
        документированной схеме HH API, как и переписка/сообщения
        Zarplata.ru/SuperJob в этом проекте."""
        response = self._client.get(f"/negotiations/{negotiation_id}/messages")
        response.raise_for_status()
        return response.json()["items"]

    def send_negotiation_message(self, negotiation_id: str, text: str) -> None:
        """НЕ проверено вызовом на живом аккаунте, см.
        list_negotiation_messages."""
        response = self._client.post(
            f"/negotiations/{negotiation_id}/messages",
            data={"message": text},
        )
        response.raise_for_status()

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
