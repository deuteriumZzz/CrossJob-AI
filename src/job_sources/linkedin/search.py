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
    подобранный вслепую через скрейпинг)."""
    params = {"keywords": keywords, "f_AL": "true"}
    if location:
        params["location"] = location
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
        title_el = card.select_one(
            ".job-card-list__title, .base-search-card__title"
        )
        if not title_el:
            continue
        seen_ids.add(job_id)
        company_el = card.select_one(
            ".job-card-container__company-name, .base-search-card__subtitle"
        )

        jobs.append(
            Job(
                role=title_el.get_text(strip=True),
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
