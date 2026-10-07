from __future__ import annotations

import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

from selenium import webdriver
from selenium.webdriver.common.by import By

from src.job_sources.block_detection import raise_if_blocked, visible_text
from src.job_sources.html_text import html_letter_to_plain_text
from src.utils.chrome_utils import init_browser, is_driver_dead

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
        # ponytail: та же проверка живости driver'а, что у
        # HeadHunterBrowserClient — общая chrome_utils.is_driver_dead.
        if self._driver is not None:
            if is_driver_dead(self._driver):
                self._driver = init_browser(self.profile_dir)
            return self._driver, False
        return init_browser(self.profile_dir), True

    def search_vacancies_html(
        self, query: str, page: int = 1, filters: Optional[dict] = None
    ) -> str:
        driver, owns_it = self._acquire_driver()
        try:
            path = "/vacancies" if page == 1 else f"/vacancies/{page}"
            params = {**(filters or {}), "qs": query}
            driver.get(f"{GJ_BASE}{path}?{urlencode(params)}")
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

    def apply(
        self, vacancy_url: str, profile_dir: Path, cover_letter: str = ""
    ) -> bool:
        """Best-effort, НЕ проверено на живом аккаунте (в отличие от
        HH/GetMatch): анонимно на странице вакансии подтверждено
        только, что раздел "Откликнуться на вакансию" требует входа
        через OAuth (Google/VK/GitHub и т.д.) — Google-пароль
        пользователя вводить нельзя (см. GeekjobSession), поэтому
        реальную кнопку отправки после входа увидеть было нечем.
        Ищем кнопку с текстом "Откликнуться" внутри самой страницы
        (не якорную ссылку в шапке — та просто прокручивает к разделу)
        — если её там нет, возвращаем False и вызывающий код
        записывает как dry-run, ничего не ломая.

        ponytail: раньше клик был единственным действием — geekjob
        после клика подставляет свой дефолтный "быстрый отклик"
        (просто ссылка на резюме, без письма), сгенерированный
        cover_letter нигде не использовался. Тот же приём, что у
        GetMatchClient.apply: после клика ищем textarea (если форма её
        показала) и вписываем письмо перед тем, как искать кнопку
        отправки — если поля нет, просто остаёмся на quick-apply."""
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
            if cover_letter:
                # Подтверждено вживую 2026-10-07: поле письма (#respond-text,
                # «Измените сопроводительный текст по своему усмотрению»)
                # стоит на странице вакансии ДО нажатия «Откликнуться», сразу
                # с шаблоном geekjob; клик отправляет то, что в поле сейчас.
                # Раньше бот жал «Откликнуться» первым — уходил шаблон, а
                # письмо искалось уже после отправки и никуда не попадало.
                # Нет поля или письмо не вписалось — не отправляем вовсе
                # (исключение: вызывающий код пропускает вакансию без записи
                # в журнал, и следующий прогон попробует снова).
                letter = html_letter_to_plain_text(cover_letter)
                boxes = [
                    t
                    for t in driver.find_elements(By.TAG_NAME, "textarea")
                    if t.is_displayed()
                ]
                if not boxes:
                    raise RuntimeError(
                        "geekjob: поле сопроводительного письма не найдено "
                        "— отклик не отправлен"
                    )
                boxes[0].clear()
                boxes[0].send_keys(letter)
                if not (boxes[0].get_attribute("value") or "").strip():
                    raise RuntimeError(
                        "geekjob: письмо не вставилось в поле — отклик не "
                        "отправлен"
                    )
            buttons[0].click()
            time.sleep(1)
            if cover_letter:
                # Двухшаговая форма: после клика может появиться «Отправить».
                submit_buttons = driver.find_elements(
                    By.XPATH,
                    '//button[contains(normalize-space(), "Отправить")]',
                )
                if submit_buttons:
                    submit_buttons[0].click()
                    time.sleep(1)
            return True
        finally:
            driver.quit()
