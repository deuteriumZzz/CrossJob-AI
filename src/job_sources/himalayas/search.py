import re
import time
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from src.job import Job
from src.job_sources.block_detection import (
    raise_if_blocked,
    raise_if_blocked_after_wait,
)
from src.job_sources.himalayas.mapping import _JOB_LINK_RE, parse_search_html
from src.job_sources.html_text import strip_html
from src.utils.chrome_utils import get_with_retry

SEARCH_URL = "https://himalayas.app/jobs"
# Официальный публичный JSON-поиск (20 на страницу, ?page=N) — без
# Cloudflare и сразу с описанием. Страница /jobs/{slug} за Cloudflare
# отдавала ~1 вакансию за ход, API — тысячи (1.11).
API_SEARCH_URL = "https://himalayas.app/jobs/api/search"
PAGE_LOAD_WAIT_SECONDS = 4
SCROLL_PAUSE_SECONDS = 1.5
SCROLL_STEPS = 5
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(position: str) -> str:
    return _SLUG_RE.sub("-", position.strip().lower()).strip("-")


def search_jobs(driver, position: str, query: str = "") -> list[Job]:
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
    url = f"{SEARCH_URL}/{slug}" if slug else SEARCH_URL
    if query:
        url += "?" + query.lstrip("&")
    get_with_retry(driver, url, retries=1, pause_seconds=5)
    time.sleep(PAGE_LOAD_WAIT_SECONDS)
    raise_if_blocked_after_wait(driver)

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


def search_jobs_api(position: str, page: int = 1) -> list[Job]:
    response = httpx.get(
        API_SEARCH_URL,
        params={"q": position, "page": page},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    raise_if_blocked(response)
    response.raise_for_status()
    jobs: list[Job] = []
    for item in response.json().get("jobs") or []:
        match = _JOB_LINK_RE.match(urlparse(item.get("guid") or "").path)
        if not match:
            continue
        company_slug, job_slug = match.groups()
        jobs.append(
            Job(
                role=item.get("title") or "",
                company=item.get("companyName") or "",
                location=", ".join(item.get("locationRestrictions") or []),
                link=item["guid"],
                description=strip_html(item.get("description") or ""),
                source="himalayas",
                external_id=f"{company_slug}/{job_slug}",
                apply_method="himalayas_manual",
            )
        )
    return jobs
