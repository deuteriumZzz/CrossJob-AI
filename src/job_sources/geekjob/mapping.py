from bs4 import BeautifulSoup

from src.job import Job

GJ_BASE_URL = "https://geekjob.ru"


def parse_search_results(html: str) -> list[dict]:
    """Извлекает {id, title} для каждой карточки на странице поиска
    /vacancies."""
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen_ids = set()
    for link in soup.select("p.vacancy-name a.title"):
        href = str(link.get("href", ""))
        vacancy_id = href.rstrip("/").rsplit("/", 1)[-1]
        if not vacancy_id or vacancy_id in seen_ids:
            continue
        seen_ids.add(vacancy_id)
        results.append({"id": vacancy_id, "title": link.get_text(strip=True)})
    return results


def geekjob_vacancy_to_job(html: str, vacancy_id: str) -> Job:
    """Преобразует страницу /vacancy/{id} в Job. apply_method равен
    "geekjob_manual" — автоматического отклика для этого источника
    пока нет."""
    soup = BeautifulSoup(html, "html.parser")

    title = soup.select_one("h1")
    company_link = soup.select_one("h5.company-name a[href^='/company/']")
    company_site = soup.select_one("h5.company-name a#company-web")
    location = soup.select_one("div.location")
    description = soup.select_one("#vacancy-description")
    salary = soup.select_one("div.jobinfo span.salary")

    return Job(
        role=title.get_text(strip=True) if title else "",
        company=company_link.get_text(strip=True) if company_link else "",
        location=location.get_text(strip=True) if location else "",
        link=f"{GJ_BASE_URL}/vacancy/{vacancy_id}",
        description=(
            description.get_text("\n", strip=True) if description else ""
        ),
        source="geekjob",
        external_id=vacancy_id,
        salary=salary.get_text(strip=True) if salary else "",
        company_url=(
            str(company_site.get("href", "")) if company_site else ""
        ),
        apply_method="geekjob_manual",
    )
