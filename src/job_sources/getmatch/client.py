import time
from pathlib import Path
from typing import Optional

from selenium.webdriver.common.by import By

from src.job_sources.block_detection import raise_if_blocked
from src.utils.chrome_utils import init_browser

GM_BASE = "https://getmatch.ru"
# ponytail: фиксированный sleep вместо явного ожидания элемента,
# подтверждено, что 4с достаточно для рендера карточек вакансий на живом
# прогоне; увеличить, если на медленном соединении результаты приходят
# пустыми.
PAGE_LOAD_WAIT_SECONDS = 4


class GetMatchClient:
    """GetMatch — это SPA на Next.js с клиентским рендерингом: в
    исходном HTML вообще нет данных о вакансиях (подтверждено прямым
    запросом: 0 ссылок на вакансии до выполнения JS), поэтому здесь
    используется настоящий браузер Selenium вместо httpx, в отличие
    от остальных скрейперов. profile_dir (если передан) даёт Chrome
    постоянный профиль вместо чистого запуска каждый раз — см.
    src/utils/chrome_utils.py."""

    def __init__(self, profile_dir: Optional[Path] = None):
        self.profile_dir = profile_dir

    def search_vacancies_html(self, query: str) -> str:
        driver = init_browser(self.profile_dir)
        try:
            driver.get(f"{GM_BASE}/vacancies?q={query}")
            time.sleep(PAGE_LOAD_WAIT_SECONDS)
            page_source = driver.page_source
            raise_if_blocked(page_source)
            return page_source
        finally:
            driver.quit()

    def apply(self, vacancy_url: str, cover_letter: str = "") -> bool:
        """Клик на "Откликнуться" почти всегда открывает модалку с
        зарплатой/локацией (обе уже подставлены из профиля — ничего
        не трогаем) и полем "Сопроводительное письмо" — подтверждено
        скриншотом реального аккаунта; вписываем письмо и жмём
        "Отправить отклик". На случай редкого прямого one-click без
        модалки (старое поведение) — если textarea/кнопка отправки не
        нашлись, всё равно возвращаем True: сам клик на "Откликнуться"
        уже засчитан площадкой. Требует, чтобы
        GetMatchSession.ensure_logged_in() уже был пройден для этого
        profile_dir — иначе кнопки "Откликнуться" не будет (форма
        входа), и apply() вернёт False."""
        driver = init_browser(self.profile_dir)
        try:
            driver.get(vacancy_url)
            time.sleep(PAGE_LOAD_WAIT_SECONDS)
            page_source = driver.page_source
            raise_if_blocked(page_source)
            buttons = driver.find_elements(
                By.XPATH, '//button[normalize-space()="Откликнуться"]'
            )
            if not buttons:
                return False
            buttons[0].click()
            time.sleep(1.5)

            if cover_letter:
                textareas = driver.find_elements(By.TAG_NAME, "textarea")
                if textareas:
                    textareas[0].send_keys(cover_letter)

            submit_buttons = driver.find_elements(
                By.XPATH, '//button[normalize-space()="Отправить отклик"]'
            )
            if submit_buttons:
                submit_buttons[0].click()
                time.sleep(1.5)
            return True
        finally:
            driver.quit()
