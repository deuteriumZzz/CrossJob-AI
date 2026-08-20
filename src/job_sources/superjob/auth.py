from __future__ import annotations

from pathlib import Path

import httpx

from src.job_sources.oauth_browser_flow import BrowserOAuthFlow

# Эндпоинты проверены по официальному PHP-клиенту
# (github.com/superjobru/superjob-api-client, SuperjobAPI.php):
# OAUTH_AUTHORIZE_URL, OAUTH_URL.'access_token'/'refresh_token'
# (GET, а не POST).
SJ_OAUTH_AUTHORIZE_URL = "https://www.superjob.ru/authorize"
SJ_OAUTH_TOKEN_URL = "https://api.superjob.ru/2.0/oauth2/access_token/"
SJ_OAUTH_REFRESH_URL = "https://api.superjob.ru/2.0/oauth2/refresh_token/"
# Должен быть зарегистрирован именно в таком виде в настройках
# приложения в админке SuperJob.
REDIRECT_URI = "https://www.superjob.ru"


class SuperJobAuth:
    """OAuth2 для личного аккаунта superjob.ru. Первый запуск требует
    интерактивного входа через браузер; дальше refresh-токен позволяет
    обходиться без него."""

    def __init__(self, client_id: str, client_secret: str, token_path: Path):
        def exchange_code(code: str) -> dict:
            response = httpx.get(
                SJ_OAUTH_TOKEN_URL,
                params={
                    "code": code,
                    "redirect_uri": REDIRECT_URI,
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
            )
            response.raise_for_status()
            return response.json()

        def refresh(refresh_token: str) -> dict:
            response = httpx.get(
                SJ_OAUTH_REFRESH_URL,
                params={
                    "refresh_token": refresh_token,
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
            )
            response.raise_for_status()
            return response.json()

        self._flow = BrowserOAuthFlow(
            authorize_url=SJ_OAUTH_AUTHORIZE_URL,
            authorize_params={
                "client_id": client_id,
                "redirect_uri": REDIRECT_URI,
            },
            token_path=token_path,
            exchange_code=exchange_code,
            refresh=refresh,
        )

    def get_access_token(self) -> str:
        return self._flow.get_access_token()
