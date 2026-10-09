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

from src.job_sources.block_detection import (
    raise_if_blocked,
    raise_if_page_blocked,
    visible_text,
)
from src.job_sources.hirify.mapping import (
    BASE_URL,
    channels_from_links,
    contacts_block,
)
from src.job_sources.user_agents import random_user_agent
from src.logging import logger
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


_CONTACT_BUTTON_TEXTS = ("показать контакты", "контакты")


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
        """{text, channels, needs_login}: нажимает «Показать контакты» в
        окне с вашим входом и читает окно «Ссылки для отклика» (email, ссылки
        HR); channels — Telegram-каналы, из которых взята вакансия (ссылки
        t.me/<канал>/<пост> на странице). needs_login — сайт просит войти
        (вы не вошли в профиль бота)."""
        driver = self._acquire_driver()
        # В свёрнутом окне страница считает себя скрытой и окно контактов не
        # открывает (проверено вживую 2026-10-08). Сдвигаем окно за левый
        # край экрана: страница «видна», пользователю окно почти не видно.
        try:
            driver.set_window_rect(x=-3000, y=0, width=1280, height=900)
        except Exception as e:
            logger.debug(f"Hirify: окно не сдвинулось: {e}")
        try:
            return self._read_contacts(driver, job_id, slug)
        finally:
            try:
                driver.minimize_window()
            except Exception:
                pass

    def _read_contacts(self, driver, job_id: str, slug: str) -> dict:
        driver.get(f"{BASE_URL}/jobs/{job_id}-{slug}")
        time.sleep(PAGE_WAIT_SECONDS)
        raise_if_page_blocked(driver)
        # Дополнительные источники скрыты за «· ещё N источник» — раскрываем.
        driver.execute_script(
            "const b=[...document.querySelectorAll('button')].find(b=>"
            "/ещё \\d+ источник/i.test(b.innerText||''));if(b)b.click();"
        )
        hrefs = driver.execute_script(
            "return [...document.querySelectorAll('a[href]')].map(a=>a.href)"
        )
        # Кнопка называется «Контакты» (жёлтая, со стрелкой) или «Показать
        # контакты» — у вошедшего и у гостя по-разному; может быть и ссылкой.
        buttons = [
            b
            for b in driver.find_elements(By.CSS_SELECTOR, "button, a")
            if b.is_displayed()
            and (b.text or "")
            .strip()
            .lower()
            .lstrip("→›>↗ ")
            .startswith(_CONTACT_BUTTON_TEXTS)
            # Ссылка «Контакты» из меню сайта уводит на другую страницу —
            # годятся только кнопки и ссылки без перехода.
            and (
                b.tag_name == "button"
                or (b.get_attribute("href") or "#").rstrip("/").endswith("#")
                or b.get_attribute("role") == "button"
            )
        ]
        text = ""
        needs_login = False
        for button in buttons[:1]:
            driver.execute_script("arguments[0].click();", button)
            for _ in range(10):  # окно с контактами подгружается
                time.sleep(1)
                page_text = visible_text(driver)
                lowered = page_text.lower()
                if any(m in lowered for m in _LOGIN_MARKERS):
                    needs_login = True
                    break
                text = contacts_block(page_text)
                if text and "загружаем" not in text.lower():
                    break
                text = ""
            driver.execute_script(
                "document.dispatchEvent(new KeyboardEvent('keydown',"
                "{key:'Escape'}));"
            )
        # Диагностика (9.10: вакансии попадали в Базу без контактов, причину
        # снаружи не видно): что нашли и чем кончилось.
        logger.info(
            f"Hirify {job_id}: кнопка «Показать контакты» — "
            f"{'есть' if buttons else 'НЕТ'}, текст контактов "
            f"{len(text)} симв., вход нужен: {needs_login}"
        )
        if buttons and not text and not needs_login:
            try:
                path = self.profile_dir / f"hirify_no_contacts_{job_id}.png"
                driver.save_screenshot(str(path))
                logger.info(f"Hirify {job_id}: снимок страницы — {path}")
            except Exception:
                pass
        return {
            "text": text,
            "channels": channels_from_links(hrefs),
            "needs_login": needs_login,
        }
