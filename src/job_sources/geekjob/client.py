from __future__ import annotations

import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

from selenium import webdriver
from selenium.webdriver.common.by import By

from src.job_sources.block_detection import raise_if_blocked, visible_text
from src.utils.chrome_utils import init_browser

GJ_BASE = "https://geekjob.ru"
PAGE_LOAD_WAIT_SECONDS = 4


class GeekjobClient:
    """geekjob.ru — Vue.js SPA: результаты поиска (?qs=...) рендерятся
    только на клиенте. Подтверждено вживую: httpx без исполнения JS
    получал 0 карточек вакансий на странице поиска, тот же URL через
    Selenium с ожиданием рендера — 37. Раньше здесь был httpx с
    неверным именем параметра (q вместо qs) вдобавок — оба бага
    вместе означали, что поиск всегда возвращал один и тот же
    дефолтный список вакансий независимо от запроса. apply() ниже уже
    был на Selenium с самого начала — теперь и поиск идёт через тот
    же механизм вместо httpx.

    ponytail: используйте как контекстный менеджер (`with
    GeekjobClient(profile_dir) as client:`), чтобы один Chrome
    переиспользовался на весь поиск (много страниц + карточек
    вакансий), а не открывался заново на каждый запрос — тот же
    паттерн, что у HeadHunterBrowserClient. apply() создаёт свой
    драйвер отдельно (вызывается по одному разу на реальный отклик,
    а не в цикле поиска)."""

    def __init__(self, profile_dir: Path):
        self.profile_dir = profile_dir
        self._driver: Optional[webdriver.Chrome] = None

    def __enter__(self) -> "GeekjobClient":
        self._driver = init_browser(self.profile_dir)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._driver is not None:
            self._driver.quit()
            self._driver = None

    def _acquire_driver(self):
        if self._driver is not None:
            return self._driver, False
        return init_browser(self.profile_dir), True

    def search_vacancies_html(self, query: str, page: int = 1) -> str:
        driver, owns_it = self._acquire_driver()
        try:
            path = "/vacancies" if page == 1 else f"/vacancies/{page}"
            driver.get(f"{GJ_BASE}{path}?{urlencode({'qs': query})}")
            time.sleep(PAGE_LOAD_WAIT_SECONDS)
            raise_if_blocked(visible_text(driver))
            return driver.page_source
        finally:
            if owns_it:
                driver.quit()

    def get_vacancy_html(self, vacancy_id: str) -> str:
        driver, owns_it = self._acquire_driver()
        try:
            driver.get(f"{GJ_BASE}/vacancy/{vacancy_id}")
            time.sleep(PAGE_LOAD_WAIT_SECONDS)
            raise_if_blocked(visible_text(driver))
            return driver.page_source
        finally:
            if owns_it:
                driver.quit()

    def apply(self, vacancy_url: str, profile_dir: Path) -> bool:
        """Best-effort, НЕ проверено на живом аккаунте (в отличие от
        HH/GetMatch): анонимно на странице вакансии подтверждено
        только, что раздел "Откликнуться на вакансию" требует входа
        через OAuth (Google/VK/GitHub и т.д.) — Google-пароль
        пользователя вводить нельзя (см. GeekjobSession), поэтому
        реальную кнопку отправки после входа увидеть было нечем.
        Ищем кнопку с текстом "Откликнуться" внутри самой страницы
        (не якорную ссылку в шапке — та просто прокручивает к разделу)
        — если её там нет, возвращаем False и вызывающий код
        записывает как dry-run, ничего не ломая."""
        driver = init_browser(profile_dir)
        try:
            driver.get(vacancy_url)
            time.sleep(PAGE_LOAD_WAIT_SECONDS)
            raise_if_blocked(visible_text(driver))
            buttons = driver.find_elements(
                By.XPATH,
                '//button[contains(normalize-space(), "Откликнуться")]',
            )
            if not buttons:
                return False
            buttons[0].click()
            time.sleep(1)
            return True
        finally:
            driver.quit()
