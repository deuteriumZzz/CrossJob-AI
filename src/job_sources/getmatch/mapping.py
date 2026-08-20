from bs4 import BeautifulSoup

from src.job import Job

GM_BASE_URL = "https://getmatch.ru"


def parse_search_results(html: str) -> list[Job]:
    """Извлекает вакансии с отрендеренной страницы поиска GetMatch
    /vacancies. Используются только стабильные, семантические имена
    классов (b-vacancy-card-*) — классы из CSS-модулей вида
    tag-module__<hash>__title намеренно не используются, так как хеш
    меняется при каждой сборке фронтенда GetMatch."""
    soup = BeautifulSoup(html, "html.parser")
    jobs = []

    for card in soup.select("div.b-vacancy-card"):
        title_link = card.select_one(".b-vacancy-card-title h3 a")
        if not title_link:
            continue

        href = str(title_link.get("href", "")).split("?", 1)[0]
        vacancy_id = href.rsplit("/", 1)[-1].split("-", 1)[0]

        company_link = card.select_one(".b-vacancy-card-title h4 a")
        location = card.select_one(".b-vacancy-locations")
        description = card.select_one(".b-vacancy-card-description")
        salary = card.select_one(".b-vacancy-card-subtitle__salary")

        jobs.append(
            Job(
                role=title_link.get_text(strip=True),
                company=(
                    company_link.get_text(strip=True) if company_link else ""
                ),
                location=(
                    location.get_text(" ", strip=True) if location else ""
                ),
                link=f"{GM_BASE_URL}{href}",
                description=(
                    description.get_text(" ", strip=True)
                    if description
                    else ""
                ),
                source="getmatch",
                external_id=vacancy_id,
                salary=salary.get_text(" ", strip=True) if salary else "",
                apply_method="getmatch_manual",
            )
        )

    return jobs
