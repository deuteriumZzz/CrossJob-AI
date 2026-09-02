import re
import time

from bs4 import BeautifulSoup

from src.job import Job
from src.job_sources.himalayas.mapping import parse_search_html

SEARCH_URL = "https://himalayas.app/jobs"
PAGE_LOAD_WAIT_SECONDS = 4
SCROLL_PAUSE_SECONDS = 1.5
SCROLL_STEPS = 5
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(position: str) -> str:
    return _SLUG_RE.sub("-", position.strip().lower()).strip("-")


def search_jobs(driver, position: str) -> list[Job]:
    """НЕ подтверждено на живой сессии: /jobs и /companies/... на
    himalayas.app отдают анти-бот интерстишл для запроса без реального
    браузерного отпечатка (подтверждено вживую 2026-09-02, см. docstring
    init_himalayas_browser) — undetected-chromedriver должен проходить
    его так же, как проходит LinkedIn, но это не проверено с реальным
    залогиненным аккаунтом. Селекторы карточек ниже — лучшее
    предположение по структуре ссылок (/companies/{company}/jobs/{slug},
    подтверждено косвенно через публичную выдачу поиска), а не сверены
    визуально на живой странице — при первом реальном прогоне проверьте
    лог "Found N matching himalayas.app vacancies" и при 0 результатах
    смотрите разметку вручную и правьте эту функцию."""
    slug = _slugify(position)
    driver.get(f"{SEARCH_URL}/{slug}" if slug else SEARCH_URL)
    time.sleep(PAGE_LOAD_WAIT_SECONDS)

    for _ in range(SCROLL_STEPS):
        driver.execute_script(
            "window.scrollTo(0, document.body.scrollHeight);"
        )
        time.sleep(SCROLL_PAUSE_SECONDS)

    return parse_search_html(driver.page_source)


def load_job_description(driver, job: Job) -> Job:
    driver.get(job.link)
    time.sleep(PAGE_LOAD_WAIT_SECONDS)
    soup = BeautifulSoup(driver.page_source, "html.parser")
    main = soup.find("main") or soup.find("article") or soup.body
    if main:
        job.description = main.get_text("\n", strip=True)
    return job
