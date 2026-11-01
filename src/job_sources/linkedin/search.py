import time
from typing import Optional
from urllib.parse import urlencode

import httpx
from bs4 import BeautifulSoup

from src.job import Job
from src.job_sources.filters import linkedin_search_params
from src.job_sources.user_agents import random_user_agent

SEARCH_URL = "https://www.linkedin.com/jobs/search/"
_WORK_TYPE_LABELS = {"1": "on-site", "2": "remote", "3": "hybrid"}
# Новая выдача (1.11) молча выбрасывает текстовый location=… и ищет у
# локации профиля (Индонезия) — регион понимает только как geoId.
# Сверено вживую: США → New York/Denver…, ЕС → Польша/Литва/Румыния.
_GEO_IDS = {
    "united states": "103644278",
    "usa": "103644278",
    "european union": "91000000",
    "eu": "91000000",
    "worldwide": "92000000",
    # Сверено вживую 1.11 (выдача из этих стран). Удалёнки там мало:
    # на первой странице UK 4/12, Канада 2/17, Израиль и Сингапур 0.
    "united kingdom": "101165590",
    "uk": "101165590",
    "canada": "101174742",
    "australia": "101452733",
    "israel": "101620260",
    "united arab emirates": "104305776",
    "uae": "104305776",
    "singapore": "102454443",
}
SCROLL_PAUSE_SECONDS = 1.5
SCROLL_STEPS = 8
PAGE_SIZE = 25
MAX_PAGES = 20  # до 500 карточек на запрос
_SCROLL_JS = """
let el = document.querySelector(
  '[data-job-id], [componentkey^="job-card-component-ref-"]');
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
    # Новая выдача (/jobs/search-results/, 1.11) подменяет f_WT своим
    # фильтром и оставляет ~31 вакансию вместо тысяч — формат работы
    # проверяем сами по пометке в карточке «(Remote)/(Hybrid)/(On-site)».
    work_types = {
        _WORK_TYPE_LABELS[code]
        for code in params.pop("f_WT", "").split(",")
        if code in _WORK_TYPE_LABELS
    }
    geo_id = _GEO_IDS.get(location.strip().lower(), "92000000")
    if location and location.strip().lower() not in _GEO_IDS:
        geo_id = location if location.isdigit() else ""
        if not geo_id:
            params["location"] = location
    if geo_id:
        params["geoId"] = geo_id
    jobs: list[Job] = []
    seen_ids: set = set()
    # Выдача — страницами по 25 (start=0, 25, 50…): раньше читалась только
    # первая, и бот видел 7–9 карточек вместо сотен. Идём, пока страница
    # приносит новые карточки.
    # Регионов много — страниц на каждый меньше (linkedin.pages_per_location),
    # иначе ход LinkedIn тянется больше часа (~20 с на страницу).
    max_pages = int(
        ((preferences or {}).get("linkedin") or {}).get(
            "pages_per_location", MAX_PAGES
        )
    )
    for page in range(max_pages):
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
        # С 22.10 залогиненный LinkedIn редиректит на /jobs/search-results/
        # с новой разметкой: data-job-id нет, классы обфусцированы — id
        # только в componentkey, поля — первые <p> карточки (название,
        # компания, место; сверено вживую 1.11). Без этого — 0 карточек.
        for card in soup.select('[componentkey^="job-card-component-ref-"]'):
            job_id = card["componentkey"].rsplit("-", 1)[-1]
            if not job_id.isdigit() or job_id in seen_ids:
                continue
            fields = [p.get_text(" ", strip=True) for p in card.find_all("p")]
            if not fields or not fields[0]:
                continue
            location = fields[2] if len(fields) > 2 else ""
            label = location.rsplit("(", 1)[-1].rstrip(")").lower()
            if work_types and "(" in location and label not in work_types:
                seen_ids.add(job_id)
                added += 1  # карточка на странице есть — выдача не кончилась
                continue
            seen_ids.add(job_id)
            added += 1
            jobs.append(
                Job(
                    role=fields[0],
                    company=fields[1] if len(fields) > 1 else "",
                    location=location,
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
