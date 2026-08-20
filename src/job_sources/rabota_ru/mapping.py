import re

from bs4 import BeautifulSoup

from src.job import Job
from src.job_sources.html_text import strip_html

RR_BASE_URL = "https://rabota.ru"
_VACANCY_ID_RE = re.compile(r"/vacancy/(\d+)/")


def parse_search_results(html: str) -> list[dict]:
    """Извлекает {id, title} для каждой карточки на странице поиска
    /vacancy/."""
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen_ids = set()
    for link in soup.select('[itemprop="title"] a[href^="/vacancy/"]'):
        match = _VACANCY_ID_RE.search(str(link.get("href", "")))
        if not match:
            continue
        vacancy_id = match.group(1)
        if vacancy_id in seen_ids:
            continue
        seen_ids.add(vacancy_id)
        results.append({"id": vacancy_id, "title": link.get_text(strip=True)})
    return results


def rabota_ru_vacancy_to_job(html: str, vacancy_id: str) -> Job:
    """Преобразует страницу /vacancy/{id}/ (микроразметка schema.org
    JobPosting) в Job. apply_method равен "rabota_ru_manual" —
    автоматического отклика для этого источника пока нет (почему —
    см. докстринг source.py)."""
    soup = BeautifulSoup(html, "html.parser")

    title = soup.select_one('[itemprop="title"]')
    company = soup.select_one(
        '[itemprop="hiringOrganization"] [itemprop="name"]'
    )
    location = soup.select_one('[itemprop="jobLocation"]')
    description = soup.select_one('[itemprop="description"]')

    return Job(
        role=title.get_text(strip=True) if title else "",
        company=company.get_text(strip=True) if company else "",
        location=location.get_text(strip=True) if location else "",
        link=f"{RR_BASE_URL}/vacancy/{vacancy_id}/",
        description=strip_html(str(description)) if description else "",
        source="rabota_ru",
        external_id=vacancy_id,
        apply_method="rabota_ru_manual",
    )
