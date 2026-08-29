import time
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from src.job import Job

SEARCH_URL = "https://www.linkedin.com/jobs/search/"
SCROLL_PAUSE_SECONDS = 1.5
SCROLL_STEPS = 5


def search_easy_apply_jobs(driver, keywords: str, location: str) -> list[Job]:
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
    params = {"keywords": keywords, "f_AL": "true", "f_WT": "2"}
    if location:
        params["location"] = location
    else:
        params["geoId"] = "92000000"
    driver.get(f"{SEARCH_URL}?{urlencode(params)}")
    time.sleep(3)

    for _ in range(SCROLL_STEPS):
        driver.execute_script(
            "window.scrollTo(0, document.body.scrollHeight);"
        )
        time.sleep(SCROLL_PAUSE_SECONDS)

    soup = BeautifulSoup(driver.page_source, "html.parser")
    jobs = []
    seen_ids = set()
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
        company_el = card.select_one(".artdeco-entity-lockup__subtitle")

        jobs.append(
            Job(
                role=title,
                company=company_el.get_text(strip=True) if company_el else "",
                location="",
                link=f"https://www.linkedin.com/jobs/view/{job_id}/",
                description="",
                source="linkedin",
                external_id=job_id,
                apply_method="linkedin_easy_apply",
            )
        )

    return jobs


def load_job_description(driver, job: Job) -> Job:
    driver.get(job.link)
    time.sleep(2)
    soup = BeautifulSoup(driver.page_source, "html.parser")
    description = soup.select_one(
        ".jobs-description__content, .jobs-box__html-content"
    )
    if description:
        job.description = description.get_text("\n", strip=True)
    return job
