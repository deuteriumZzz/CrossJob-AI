from __future__ import annotations

from pathlib import Path

import httpx

from src.job_sources.oauth_browser_flow import BrowserOAuthFlow

# ponytail: та же оговорка, что и в client.py — выведено по шаблону
# hh.ru для брендовых сайтов HeadHunter-Group, не проверено на живом
# приложении zarplata.ru.
ZP_OAUTH_AUTHORIZE_URL = "https://zarplata.ru/oauth/authorize"
ZP_OAUTH_TOKEN_URL = "https://zarplata.ru/oauth/token"
REDIRECT_URI = "https://zarplata.ru"


class ZarplataAuth:
    """OAuth2 для личного аккаунта zarplata.ru. Первый запуск требует
    интерактивного входа через браузер; дальше refresh-токен позволяет
    обходиться без него."""

    def __init__(self, client_id: str, client_secret: str, token_path: Path):
        def exchange_code(code: str) -> dict:
            response = httpx.post(
                ZP_OAUTH_TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "redirect_uri": REDIRECT_URI,
                },
            )
            response.raise_for_status()
            return response.json()

        def refresh(refresh_token: str) -> dict:
            response = httpx.post(
                ZP_OAUTH_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
            )
            response.raise_for_status()
            return response.json()

        self._flow = BrowserOAuthFlow(
            authorize_url=ZP_OAUTH_AUTHORIZE_URL,
            authorize_params={
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": REDIRECT_URI,
            },
            token_path=token_path,
            exchange_code=exchange_code,
            refresh=refresh,
        )

    def get_access_token(self) -> str:
        return self._flow.get_access_token()
