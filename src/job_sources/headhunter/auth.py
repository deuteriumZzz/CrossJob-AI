from __future__ import annotations

from pathlib import Path

import httpx

from src.job_sources.oauth_browser_flow import BrowserOAuthFlow

HH_OAUTH_AUTHORIZE_URL = "https://hh.ru/oauth/authorize"
HH_OAUTH_TOKEN_URL = "https://hh.ru/oauth/token"
REDIRECT_URI = "https://hh.ru/oauth/blank.html"


class HHAuth:
    """OAuth2 для личного аккаунта hh.ru. Первый запуск требует
    интерактивного входа через браузер; дальше refresh-токен позволяет
    обходиться без него."""

    def __init__(self, client_id: str, client_secret: str, token_path: Path):
        def exchange_code(code: str) -> dict:
            response = httpx.post(
                HH_OAUTH_TOKEN_URL,
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
                HH_OAUTH_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
            )
            response.raise_for_status()
            return response.json()

        self._flow = BrowserOAuthFlow(
            authorize_url=HH_OAUTH_AUTHORIZE_URL,
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
