import time
from pathlib import Path
from typing import Callable

from selenium.webdriver.common.by import By

from src.job_sources.block_detection import raise_if_blocked, visible_text
from src.job_sources.html_text import html_letter_to_plain_text
from src.utils.chrome_utils import init_browser

HH_BASE = "https://hh.ru"
# Российский регион целиком — переопределяет сохранённый в аккаунте
# фильтр по конкретному городу, потому что кандидат работает удалённо
# и город не должен ограничивать поиск.
HH_AREA_RUSSIA = "113"
PAGE_LOAD_WAIT_SECONDS = 4


class HeadHunterBrowserClient:
    """Поиск и отклик через настоящую браузерную сессию hh.ru вместо
    официального API (см. HeadHunterSession — почему). profile_dir
    обязателен: без него нет доступа к вошедшему аккаунту."""

    def __init__(self, profile_dir: Path):
        self.profile_dir = profile_dir

    def search_vacancies_html(
        self, query: str, remote_only: bool, page: int = 0
    ) -> str:
        driver = init_browser(self.profile_dir)
        try:
            params = f"text={query}&area={HH_AREA_RUSSIA}&page={page}"
            if remote_only:
                params += "&schedule=remote"
            driver.get(f"{HH_BASE}/search/vacancy?{params}")
            time.sleep(PAGE_LOAD_WAIT_SECONDS)
            raise_if_blocked(visible_text(driver))
            return driver.page_source
        finally:
            driver.quit()

    def get_vacancy_html(self, vacancy_id: str) -> str:
        driver = init_browser(self.profile_dir)
        try:
            driver.get(f"{HH_BASE}/vacancy/{vacancy_id}")
            time.sleep(PAGE_LOAD_WAIT_SECONDS)
            raise_if_blocked(visible_text(driver))
            return driver.page_source
        finally:
            driver.quit()

    def apply(
        self, vacancy_url: str, cover_letter_fn: Callable[[], str]
    ) -> tuple[bool, str]:
        """Отклик кликом на "Откликнуться" (data-qa=
        "vacancy-response-link-top", подтверждено прямым просмотром
        живой страницы вакансии). cover_letter_fn вызывается лениво —
        только если модалка реально показала поле под письмо, а не
        заранее для каждой вакансии: некоторые открываются "быстрым
        откликом" в один клик без поля, и незачем тратить LLM-вызов
        впустую, когда результат никуда не денется. Возвращает
        (True/False — была ли нажата "Откликнуться", письмо — то, что
        реально ушло, или "" если поля не было). False — если кнопки
        нет (уже откликались/вакансия недоступна) — вызывающий код
        должен записать это как dry-run, не падая."""
        driver = init_browser(self.profile_dir)
        try:
            driver.get(vacancy_url)
            time.sleep(PAGE_LOAD_WAIT_SECONDS)
            raise_if_blocked(visible_text(driver))

            buttons = driver.find_elements(
                By.CSS_SELECTOR, '[data-qa="vacancy-response-link-top"]'
            )
            if not buttons or not buttons[0].is_displayed():
                return False, ""
            buttons[0].click()
            time.sleep(2)

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
            return True, cover_letter
        finally:
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
            toggles[0].click()
            time.sleep(0.5)
        textareas = driver.find_elements(
            By.CSS_SELECTOR, 'textarea[data-qa*="letter"]'
        )
        if not textareas or not textareas[0].is_displayed():
            return ""
        cover_letter = html_letter_to_plain_text(cover_letter_fn())
        textareas[0].send_keys(cover_letter)
        return cover_letter
