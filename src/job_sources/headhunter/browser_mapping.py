from bs4 import BeautifulSoup

from src.job import Job

HH_BASE_URL = "https://hh.ru"


def parse_search_results(html: str) -> list[Job]:
    """Извлекает вакансии со страницы /search/vacancy hh.ru. data-qa
    подтверждены прямым просмотром живой страницы поиска (без входа):
    vacancy-serp__vacancy — карточка, serp-item__title — ссылка с
    заголовком, vacancy-serp__vacancy-employer-text — работодатель,
    vacancy-serp__vacancy-address — локация. Зарплата в карточках
    поиска не размечена своим data-qa (обычный <span> без атрибута) —
    не читаем её здесь; полное описание и остальные детали берутся
    отдельным запросом на странице вакансии, см. hh_html_vacancy_to_job."""
    soup = BeautifulSoup(html, "html.parser")
    jobs = []

    for card in soup.select('[data-qa="vacancy-serp__vacancy"]'):
        title_link = card.select_one('a[data-qa="serp-item__title"]')
        if not title_link:
            continue
        href = str(title_link.get("href", "")).split("?", 1)[0]
        vacancy_id = href.rstrip("/").rsplit("/", 1)[-1]
        if not vacancy_id.isdigit():
            continue

        employer = card.select_one(
            '[data-qa="vacancy-serp__vacancy-employer-text"]'
        )
        address = card.select_one('[data-qa="vacancy-serp__vacancy-address"]')

        jobs.append(
            Job(
                role=title_link.get_text(strip=True),
                company=employer.get_text(strip=True) if employer else "",
                location=address.get_text(strip=True) if address else "",
                link=f"{HH_BASE_URL}/vacancy/{vacancy_id}",
                description="",
                source="headhunter",
                external_id=vacancy_id,
                apply_method="headhunter_manual",
            )
        )

    return jobs


def hh_html_vacancy_to_job(html: str, vacancy_id: str) -> Job:
    """Заполняет описание/зарплату по странице /vacancy/{id}. data-qa
    для заголовка/работодателя/описания подтверждены прямым просмотром
    живой страницы вакансии; зарплата на этой конкретной проверенной
    вакансии не была указана вообще, поэтому её селектор здесь не
    проверен и не используется — ponytail: добавить, если понадобится."""
    soup = BeautifulSoup(html, "html.parser")

    title = soup.select_one('[data-qa="vacancy-title"]')
    company = soup.select_one('[data-qa="vacancy-company-name"]')
    description = soup.select_one('[data-qa="vacancy-description"]')

    return Job(
        role=title.get_text(strip=True) if title else "",
        company=company.get_text(strip=True) if company else "",
        location="",
        link=f"{HH_BASE_URL}/vacancy/{vacancy_id}",
        description=(
            description.get_text("\n", strip=True) if description else ""
        ),
        source="headhunter",
        external_id=vacancy_id,
        apply_method="headhunter_manual",
    )
