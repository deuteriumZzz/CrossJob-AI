from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Optional

from selenium import webdriver
from selenium.webdriver.common.by import By

from src.job_sources.block_detection import raise_if_blocked, visible_text
from src.job_sources.headhunter.browser_test_answer import (
    answer_full_page_questionnaire,
    answer_vacancy_test_if_present,
)
from src.job_sources.html_text import html_letter_to_plain_text
from src.logging import logger
from src.utils.chrome_utils import init_browser

HH_BASE = "https://hh.ru"
# Российский регион целиком — переопределяет сохранённый в аккаунте
# фильтр по конкретному городу, потому что кандидат работает удалённо
# и город не должен ограничивать поиск.
HH_AREA_RUSSIA = "113"
PAGE_LOAD_WAIT_SECONDS = 4


def _wait_for_any(
    driver,
    selectors: list[str],
    timeout: float = 5.0,
    interval: float = 0.5,
) -> bool:
    """Опрашивает driver каждые interval секунд, пока не появится видимый
    элемент по любому из selectors, максимум timeout секунд. Возвращает
    True, если что-то нашлось, False — если истёк таймаут (не бросает,
    страница могла просто не измениться — решение остаётся за вызывающим
    кодом). ponytail: простой bounded poll вместо WebDriverWait — заменяет
    фиксированный time.sleep(2) после клика "Откликнуться", который не
    успевал за рендером SPA (вероятная причина "отклик нигде не
    срабатывает" из предыдущего прогона)."""
    deadline = time.monotonic() + timeout
    while True:
        for selector in selectors:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            if elements and elements[0].is_displayed():
                return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(interval)


class HeadHunterBrowserClient:
    """Поиск и отклик через настоящую браузерную сессию hh.ru вместо
    официального API (см. HeadHunterSession — почему). profile_dir
    обязателен: без него нет доступа к вошедшему аккаунту.

    ponytail: используйте как контекстный менеджер (`with
    HeadHunterBrowserClient(profile_dir) as client:`), чтобы один
    Chrome-процесс переиспользовался на весь прогон (поиск + карточки
    вакансий + отклики), вместо открытия/закрытия браузера на каждый
    вызов — раньше именно так и было, отсюда жалоба "бот постоянно
    открывает и закрывает хром". Без `with` поведение как раньше
    (свой одноразовый driver на вызов) — для обратной совместимости
    с любым кодом, который создаёт клиент напрямую."""

    def __init__(self, profile_dir: Path):
        self.profile_dir = profile_dir
        self._driver: Optional[webdriver.Chrome] = None

    def __enter__(self) -> "HeadHunterBrowserClient":
        self._driver = init_browser(self.profile_dir)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._driver is not None:
            self._driver.quit()
            self._driver = None

    def _acquire_driver(self):
        """(driver, owns_it) — owns_it говорит вызывающему методу,
        нужно ли закрывать driver самому (True — обычный режим без
        `with`) или оставить открытым для следующего вызова (False —
        driver управляется __enter__/__exit__)."""
        if self._driver is not None:
            return self._driver, False
        return init_browser(self.profile_dir), True

    def search_vacancies_html(
        self, query: str, remote_only: bool, page: int = 0
    ) -> str:
        driver, owns_it = self._acquire_driver()
        try:
            params = f"text={query}&area={HH_AREA_RUSSIA}&page={page}"
            if remote_only:
                params += "&schedule=remote"
            driver.get(f"{HH_BASE}/search/vacancy?{params}")
            time.sleep(PAGE_LOAD_WAIT_SECONDS)
            raise_if_blocked(visible_text(driver))
            return driver.page_source
        finally:
            if owns_it:
                driver.quit()

    def get_vacancy_html(self, vacancy_id: str) -> str:
        driver, owns_it = self._acquire_driver()
        try:
            driver.get(f"{HH_BASE}/vacancy/{vacancy_id}")
            time.sleep(PAGE_LOAD_WAIT_SECONDS)
            raise_if_blocked(visible_text(driver))
            return driver.page_source
        finally:
            if owns_it:
                driver.quit()

    def apply(
        self,
        vacancy_url: str,
        cover_letter_fn: Callable[[], str],
        ai_answer_fn: Callable[[str], str] | None = None,
    ) -> tuple[bool, str]:
        """Отклик кликом на "Откликнуться" (data-qa=
        "vacancy-response-link-top", подтверждено прямым просмотром
        живой страницы вакансии). cover_letter_fn вызывается лениво —
        только если модалка реально показала поле под письмо, а не
        заранее для каждой вакансии: некоторые открываются "быстрым
        откликом" в один клик без поля, и незачем тратить LLM-вызов
        впустую, когда результат никуда не денется. ai_answer_fn (question
        -> answer) передаётся в answer_vacancy_test_if_present — если
        вакансия требует пройти тест/анкету перед откликом (см.
        browser_test_answer.py); без него используется эвристика без AI.
        Возвращает (True/False — была ли нажата "Откликнуться", письмо —
        то, что реально ушло, или "" если поля не было). False — если
        кнопки нет (уже откликались/вакансия недоступна) — вызывающий код
        должен записать это как dry-run, не падая."""
        driver, owns_it = self._acquire_driver()
        try:
            driver.get(vacancy_url)
            time.sleep(PAGE_LOAD_WAIT_SECONDS)
            raise_if_blocked(visible_text(driver))

            buttons = driver.find_elements(
                By.CSS_SELECTOR, '[data-qa="vacancy-response-link-top"]'
            )
            if not buttons or not buttons[0].is_displayed():
                logger.warning(
                    "Кнопка 'Откликнуться' не найдена/не видна на "
                    f"{vacancy_url} (current_url={driver.current_url}) — "
                    "либо уже откликались, либо разметка страницы "
                    "изменилась."
                )
                return False, ""
            buttons[0].click()
            _wait_for_any(
                driver,
                [
                    '[data-qa*="letter-toggle"]',
                    'textarea[data-qa*="letter"]',
                    '[data-qa="vacancy-response-submit-popup"]',
                    'button[data-qa*="response-submit"]',
                    '[data-qa*="test-question"]',
                    '[data-qa*="vacancy-response-popup-test"]',
                ],
            )

            if answer_full_page_questionnaire(driver, ai_answer_fn):
                return True, ""

            test_answered = answer_vacancy_test_if_present(
                driver, ai_answer_fn
            )

            cover_letter = self._fill_cover_letter_if_present(
                driver, cover_letter_fn
            )

            submit = driver.find_elements(
                By.CSS_SELECTOR,
                '[data-qa="vacancy-response-submit-popup"], '
                'button[data-qa*="response-submit"]',
            )
            if submit and submit[0].is_displayed():
                submit[0].click()
                time.sleep(1.5)
            elif not test_answered and not cover_letter:
                logger.warning(
                    "После клика 'Откликнуться' не нашли ни поле письма, "
                    "ни кнопку отправки, ни тест на "
                    f"{vacancy_url} (current_url={driver.current_url}) — "
                    "возможно быстрый отклик без модалки (тогда всё в "
                    "порядке) либо разметка изменилась, проверьте вручную."
                )
            return True, cover_letter
        finally:
            if owns_it:
                driver.quit()

    def bump_resume(self, resume_id: str) -> bool:
        """ponytail: аналог operations/update_resumes.py из
        s3rgeym/hh-applicant-tool (бесплатный аналог платного "Поднять
        резюме в поиске" на HH), но через клик в браузере вместо их
        захардкоженного Android-клиента API — см. обоснование в
        HeadHunterSession, почему этот проект вообще не использует
        официальный/эмулированный API HH. Селектор кнопки ("Обновить")
        НЕ подтверждён прямым просмотром живой страницы (нет доступа к
        залогиненному аккаунту с резюме) — в отличие от остальных data-qa
        в этом файле/browser_mapping.py. Проверить на реальном аккаунте
        перед тем как включать headhunter.auto_bump_resume: true;
        HH сам показывает кнопку недоступной, если обновлять ещё рано
        (обычно раз в ~4ч на резюме) — это не ошибка, просто bump_resume
        вернёт False."""
        driver, owns_it = self._acquire_driver()
        try:
            driver.get(f"{HH_BASE}/resume/{resume_id}")
            time.sleep(PAGE_LOAD_WAIT_SECONDS)
            raise_if_blocked(visible_text(driver))

            buttons = driver.find_elements(
                By.CSS_SELECTOR, '[data-qa="resume-update-button"]'
            )
            if not buttons or not buttons[0].is_displayed():
                return False
            if buttons[0].get_attribute("disabled") is not None:
                return False
            buttons[0].click()
            time.sleep(1.5)
            return True
        finally:
            if owns_it:
                driver.quit()

    def _fill_cover_letter_if_present(
        self, driver, cover_letter_fn: Callable[[], str]
    ) -> str:
        """ponytail: data-qa модалки отклика (letter-toggle/textarea) —
        из публично задокументированных паттернов разметки hh.ru, НЕ
        проверено на живой сессии (в отличие от кнопок поиска/карточки
        вакансии, см. browser_mapping.py) — живой залогиненный аккаунт
        для проверки был недоступен. Если поля не нашлись, отклик
        всё равно уходит без письма вместо падения, и cover_letter_fn
        не вызывается вообще."""
        toggles = driver.find_elements(
            By.CSS_SELECTOR, '[data-qa*="letter-toggle"]'
        )
        if toggles and toggles[0].is_displayed():
            # ponytail: обычный .click() падает с "element click
            # intercepted" — центр bounding box карточки перекрыт её
            # же дочерним текстовым div (magritte-card), подтверждено
            # дважды на живых прогонах. JS-клик бьёт прямо в DOM-узел,
            # минуя проверку перекрытия в точке клика.
            driver.execute_script("arguments[0].click();", toggles[0])
            time.sleep(0.5)
        textareas = driver.find_elements(
            By.CSS_SELECTOR, 'textarea[data-qa*="letter"]'
        )
        if not textareas or not textareas[0].is_displayed():
            return ""
        cover_letter = html_letter_to_plain_text(cover_letter_fn())
        textareas[0].send_keys(cover_letter)
        return cover_letter
