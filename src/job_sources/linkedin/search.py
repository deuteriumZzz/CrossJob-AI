import time
from typing import Optional
from urllib.parse import urlencode

import httpx
from bs4 import BeautifulSoup

from src.job import Job
from src.job_sources.filters import linkedin_search_params
from src.job_sources.user_agents import random_user_agent

SEARCH_URL = "https://www.linkedin.com/jobs/search/"
SCROLL_PAUSE_SECONDS = 1.5
SCROLL_STEPS = 8
PAGE_SIZE = 25
MAX_PAGES = 20  # до 500 карточек на запрос
_SCROLL_JS = """
let el = document.querySelector('[data-job-id]');
while (el && el !== document.body) {
  const o = getComputedStyle(el).overflowY;
  if (/(auto|scroll)/.test(o) && el.scrollHeight > el.clientHeight) {
    el.scrollTop = el.scrollHeight;
    break;
  }
  el = el.parentElement;
}
window.scrollTo(0, document.body.scrollHeight);
"""


def search_easy_apply_jobs(
    driver, keywords: str, location: str, preferences: Optional[dict] = None
) -> list[Job]:
    """f_AL=true — собственный параметр LinkedIn для фильтра "только Easy
    Apply", стабильный и широко используемый query-параметр (а не
    подобранный вслепую через скрейпинг). f_WT=2 — фильтр "только
    удалённые" (work-type): кандидат ищет исключительно remote и не
    может физически переехать без визы, локальные/гибридные вакансии
    ему не подходят в принципе. geoId=92000000 — официальный geoId
    LinkedIn для "Worldwide", подставляется только когда location не
    задан явно — подтверждено живьём: пустая строка НЕ значит "по
    всему миру" сама по себе, LinkedIn в этом случае молча подставляет
    локацию из профиля кандидата (без geoId все результаты уходили в
    Индонезию — там, где физически находится кандидат в резюме — а не
    по-настоящему worldwide, как задумывалось)."""
    # f_AL/f_WT — из единых фильтров (src/job_sources/filters.py): Easy
    # Apply, только удалённые; порядок — по релевантности, как до 7.10.
    params = {
        "keywords": keywords,
        **linkedin_search_params(preferences or {}),
    }
    if location:
        params["location"] = location
    else:
        params["geoId"] = "92000000"
    jobs: list[Job] = []
    seen_ids: set = set()
    # Выдача — страницами по 25 (start=0, 25, 50…): раньше читалась только
    # первая, и бот видел 7–9 карточек вместо сотен. Идём, пока страница
    # приносит новые карточки.
    for page in range(MAX_PAGES):
        page_params = dict(params)
        if page:
            page_params["start"] = page * PAGE_SIZE
        driver.get(f"{SEARCH_URL}?{urlencode(page_params)}")
        time.sleep(3)
        for _ in range(SCROLL_STEPS):
            # Список в залогиненном LinkedIn лежит в своей прокручиваемой
            # панели — прокрутка всей страницы подгружает только первые
            # карточки; крутим и панель, и страницу.
            driver.execute_script(_SCROLL_JS)
            time.sleep(SCROLL_PAUSE_SECONDS)

        soup = BeautifulSoup(driver.page_source, "html.parser")
        added = 0
        for card in soup.select("[data-job-id]"):
            job_id = str(card.get("data-job-id", ""))
            if not job_id.isdigit() or job_id in seen_ids:
                continue
            # ponytail: сверено на живой сессии — .job-card-list__title/
            # .base-search-card__title/.job-card-container__company-name/
            # .base-search-card__subtitle (старые селекторы) не находят ни
            # одной карточки на текущей разметке LinkedIn, 0 совпадений.
            # aria-label, а не get_text() — сам текстовый узел внутри <a>
            # задвоен (видимый <span> + <span class="visually-hidden"> с
            # тем же текстом для скринридеров), get_text() склеил бы оба.
            title_el = card.select_one(".job-card-list__title--link")
            if not title_el:
                continue
            title = str(
                title_el.get("aria-label") or title_el.get_text(strip=True)
            )
            seen_ids.add(job_id)
            added += 1
            company_el = card.select_one(".artdeco-entity-lockup__subtitle")

            jobs.append(
                Job(
                    role=title,
                    company=(
                        company_el.get_text(strip=True) if company_el else ""
                    ),
                    location="",
                    link=f"https://www.linkedin.com/jobs/view/{job_id}/",
                    description="",
                    source="linkedin",
                    external_id=job_id,
                    apply_method="linkedin_easy_apply",
                )
            )
        if not added:
            break  # выдача кончилась

    return jobs


_DESCRIPTION_SELECTORS = (
    ".jobs-description__content, .jobs-box__html-content, "
    "#job-details, [class*='jobs-description']"
)
_DESCRIPTION_HEADINGS = (
    "about the job",
    "о вакансии",
    "описание вакансии",
    "acerca del empleo",
    "über diese stelle",
    "sobre a vaga",
)
# Раздел описания у LinkedIn подгружается отдельным запросом позже шапки
# вакансии; когда сессию ограничивают, он не приходит вообще (шапка есть,
# описания нет) — тогда ждём и отдаём пустой текст, а вызывающий код
# вакансию не оценивает вслепую.
_DESCRIPTION_WAIT_SECONDS = 12

_HEADING_JS = """
const names = arguments[0];
const heads = [...document.querySelectorAll('h1,h2,h3,h4,p,span,div')].filter(
  (e) => names.includes((e.innerText || '').trim().toLowerCase())
    && (e.innerText || '').trim().length < 40);
for (const h of heads.reverse()) {
  let p = h;
  for (let i = 0; i < 8 && p.parentElement; i++) {
    p = p.parentElement;
    const text = (p.innerText || '').trim();
    if (text.length > 300) return text;
  }
}
return '';"""


def _read_description(driver) -> str:
    soup = BeautifulSoup(driver.page_source, "html.parser")
    node = soup.select_one(_DESCRIPTION_SELECTORS)
    if node and node.get_text(strip=True):
        return node.get_text("\n", strip=True)
    return (
        driver.execute_script(_HEADING_JS, list(_DESCRIPTION_HEADINGS)) or ""
    )


# Публичная (без входа) страница вакансии. С 8.10 залогиненная страница
# LinkedIn не отдаёт блок «About the job» вовсе (шапка есть, описания нет
# даже через 12 с) — гостевая отдаёт полный текст. Плюс: вакансию не
# открываем в аккаунте лишний раз, Easy Apply откроет её сам.
_GUEST_POSTING_URL = (
    "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{}"
)
_GUEST_DESCRIPTION_SELECTOR = (
    ".show-more-less-html__markup, .description__text"
)


def _guest_description(job_id: str) -> str:
    if not job_id:
        return ""
    try:
        response = httpx.get(
            _GUEST_POSTING_URL.format(job_id),
            headers={"User-Agent": random_user_agent()},
            timeout=20,
            follow_redirects=True,
        )
    except httpx.HTTPError:
        return ""
    if response.status_code != 200:
        return ""
    node = BeautifulSoup(response.text, "html.parser").select_one(
        _GUEST_DESCRIPTION_SELECTOR
    )
    return node.get_text("\n", strip=True) if node else ""


def load_job_description(driver, job: Job) -> Job:
    text = _guest_description(job.external_id)
    if text:
        job.description = text
        return job
    driver.get(job.link)
    deadline = time.monotonic() + _DESCRIPTION_WAIT_SECONDS
    while True:
        time.sleep(2)
        text = _read_description(driver)
        if text or time.monotonic() >= deadline:
            break
    job.description = text
    return job
