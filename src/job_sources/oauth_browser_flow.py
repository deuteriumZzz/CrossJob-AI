from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Callable
from urllib.parse import urlencode

import httpx

from src.logging import logger
from src.utils.chrome_utils import init_browser

LOGIN_TIMEOUT_SECONDS = 300


class BrowserOAuthFlow:
    """Общий OAuth2-вход через браузер + хранение токенов в файле —
    для площадок без серверного redirect-адреса. Первый запуск
    открывает браузер для разового логина (параметр `code` читается
    из итогового URL); дальше refresh-токен позволяет обходиться
    без браузера."""

    def __init__(
        self,
        authorize_url: str,
        authorize_params: dict,
        token_path: Path,
        exchange_code: Callable[[str], dict],
        refresh: Callable[[str], dict],
    ):
        self.authorize_url = authorize_url
        self.authorize_params = authorize_params
        self.token_path = token_path
        self._exchange_code = exchange_code
        self._refresh = refresh

    def _load_tokens(self) -> dict | None:
        if self.token_path.exists():
            return json.loads(self.token_path.read_text(encoding="utf-8"))
        return None

    def _save_tokens(self, tokens: dict) -> None:
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_path.write_text(
            json.dumps(tokens, indent=2), encoding="utf-8"
        )

    def _login_interactively(self) -> dict:
        params = urlencode(self.authorize_params)
        driver = init_browser()
        try:
            driver.get(f"{self.authorize_url}?{params}")
            logger.info(
                f"Log in at {self.authorize_url} in the opened browser "
                "window to authorize this app."
            )
            deadline = time.monotonic() + LOGIN_TIMEOUT_SECONDS
            code = None
            while code is None:
                match = re.search(r"[?&]code=([^&]+)", driver.current_url)
                if match:
                    code = match.group(1)
                elif time.monotonic() > deadline:
                    raise RuntimeError(
                        f"Timed out waiting for login at {self.authorize_url}."
                    )
                else:
                    time.sleep(1)
            return self._exchange_code(code)
        finally:
            driver.quit()

    def get_access_token(self) -> str:
        tokens = self._load_tokens()
        if tokens is None:
            tokens = self._login_interactively()
            self._save_tokens(tokens)
            return tokens["access_token"]
        try:
            tokens = self._refresh(tokens["refresh_token"])
        except httpx.HTTPStatusError:
            tokens = self._login_interactively()
        self._save_tokens(tokens)
        return tokens["access_token"]
