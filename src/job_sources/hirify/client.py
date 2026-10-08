"""Клиент hirify.me. Список и страницы вакансий — обычный HTTP (открыты).
Контакты и название Telegram-канала — только после входа: окно бота с
вашим профилем (`.chrome_profile_hirify`), вход вы делаете сами один раз
(scripts/hirify_login.py). Пароли бот не вводит и аккаунт не создаёт."""

from __future__ import annotations

import random
import time
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

import httpx
from selenium import webdriver
from selenium.webdriver.common.by import By

from src.job_sources.block_detection import raise_if_blocked, visible_text
from src.job_sources.hirify.mapping import (
    BASE_URL,
    channel_from_text,
    contacts_block,
)
from src.job_sources.user_agents import random_user_agent
from src.utils.chrome_utils import init_browser, is_driver_dead

PAGE_WAIT_SECONDS = 4
# Сайт отдаёт 429 при быстрых подряд запросах (проверено вживую): пауза
# между страницами и один повтор после ожидания.
POLITE_PAUSE_SECONDS = (1.2, 2.8)
RATE_LIMIT_WAIT_SECONDS = 25
_LOGIN_MARKERS = ("нужен аккаунт", "войти через google", "введите email")


def _raise_if_blocked(response: httpx.Response, expected: str) -> None:
    """В обычных страницах hirify есть скрипты формы входа со словом
    captcha — само по себе это не блокировка. Блок — это 429/403 или
    страница без ожидаемого содержимого (списка / разметки вакансии)."""
    if expected in response.text and response.status_code == 200:
        return
    raise_if_blocked(response)


class HirifyClient:
    def __init__(self, profile_dir: Path):
        self.profile_dir = profile_dir
        self._http = httpx.Client(
            headers={"User-Agent": random_user_agent()},
            timeout=30,
            follow_redirects=True,
        )
        self._driver: Optional[webdriver.Chrome] = None

    def __enter__(self) -> "HirifyClient":
        return self

    def __exit__(self, *exc) -> None:
        self._http.close()
        if self._driver is not None:
            try:
                self._driver.quit()
            finally:
                self._driver = None

    def _get(self, url: str, expected: str) -> str:
        time.sleep(random.uniform(*POLITE_PAUSE_SECONDS))
        response = self._http.get(url)
        if response.status_code == 429:
            time.sleep(RATE_LIMIT_WAIT_SECONDS)
            response = self._http.get(url)
        _raise_if_blocked(response, expected)
        response.raise_for_status()
        return response.text

    def list_html(self, query: str, page: int = 1) -> str:
        url = f"{BASE_URL}/?search={quote_plus(query)}"
        if page > 1:
            url += f"&page={page}"
        return self._get(url, 'href="/jobs/')

    def job_html(self, job_id: str, slug: str) -> str:
        return self._get(f"{BASE_URL}/jobs/{job_id}-{slug}", '"JobPosting"')

    def _acquire_driver(self):
        if self._driver is None or is_driver_dead(self._driver):
            self._driver = init_browser(self.profile_dir)
        return self._driver

    def show_contacts(self, job_id: str, slug: str) -> dict:
        """{text, channel, needs_login}: нажимает «Показать контакты» в окне
        с вашим входом; text — блок «Контакты», channel — Telegram-канал,
        из которого взята вакансия. needs_login — сайт просит войти (вы
        не вошли в профиль бота)."""
        driver = self._acquire_driver()
        driver.get(f"{BASE_URL}/jobs/{job_id}-{slug}")
        time.sleep(PAGE_WAIT_SECONDS)
        raise_if_blocked(visible_text(driver))
        buttons = [
            b
            for b in driver.find_elements(By.CSS_SELECTOR, "button")
            if b.is_displayed()
            and (b.text or "").strip().lower()
            in ("контакты", "показать контакты")
        ]
        for button in buttons[:1]:
            driver.execute_script("arguments[0].click();", button)
            time.sleep(2.5)
        page_text = visible_text(driver)
        lowered = page_text.lower()
        needs_login = any(marker in lowered for marker in _LOGIN_MARKERS)
        return {
            "text": "" if needs_login else contacts_block(page_text),
            "channel": "" if needs_login else channel_from_text(page_text),
            "needs_login": needs_login,
        }
