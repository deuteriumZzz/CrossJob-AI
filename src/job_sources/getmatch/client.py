import time

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
    от остальных скрейперов."""

    def search_vacancies_html(self, query: str) -> str:
        driver = init_browser()
        try:
            driver.get(f"{GM_BASE}/vacancies?q={query}")
            time.sleep(PAGE_LOAD_WAIT_SECONDS)
            return driver.page_source
        finally:
            driver.quit()
