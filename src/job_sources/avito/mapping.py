from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from src.job import Job

AVITO_BASE_URL = "https://www.avito.ru"


def _description_snippet(item, specific_params: str) -> str:
    """Карточка не даёт отдельного data-marker под текст-превью
    вакансии (подтверждено вживую 2026-09-29) — берём первый <p> длиннее
    50 символов, не совпадающий с текстом item-specific-params (график/
    выплаты/опыт, тоже <p>, но короче и известен заранее)."""
    for p in item.find_all("p"):
        text = p.get_text(" ", strip=True)
        if len(text) > 50 and text != specific_params:
            return text
    return ""


def _company_name(item) -> str:
    """Название компании — не под своим data-marker, а внутри блока с
    классом, начинающимся на "userInfoStep-" (CSS-modules хэш меняется
    от сборки к сборке, префикс — нет, подтверждено вживую 2026-09-29).
    Best-effort: пусто, если структура карточки изменится."""
    block = item.select_one('[class^="userInfoStep-"]')
    if block is None:
        return ""
    link = block.find("a")
    return link.get_text(strip=True) if link else block.get_text(strip=True)


def parse_search_html(html: str) -> list[Job]:
    """Извлекает вакансии со страницы поиска avito.ru/all/vakansii —
    подтверждено вживую 2026-09-29 (реальная выдача по "python
    developer"). Раньше здесь пропускались карточки без метки "Отклик
    с резюме" в списке — оказалось, что кнопка "Откликнуться" есть на
    самой странице вакансии почти всегда независимо от этой метки
    (подтверждено вживую реальным откликом 2026-09-29: метки в списке
    не было, кнопка на детальной странице — была), а сама метка в
    выдаче появляется нестабильно/редко. Теперь берём все карточки;
    apply.py всё равно best-effort ищет кнопку на детальной странице
    и честно возвращает dry-run, если её там нет — так вакансии без
    реальной возможности откликнуться просто не потеряются молча ещё
    на этапе списка. Детальная страница вакансии НЕ запрашивается тут
    же (только в apply.py при реальном отклике): подтверждено вживую,
    что avito.ru отдаёт "Доступ ограничен: проверка безопасности" без
    реального браузерного отпечатка (см. docstring init_avito_browser)
    — описание берём из сниппета прямо в карточке поиска, этого
    достаточно для оценки соответствия резюме."""
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[Job] = []
    seen_ids: set = set()

    for item in soup.select('[data-marker="item"]'):
        item_id = item.get("data-item-id", "")
        title_el = item.select_one('[data-marker="item-title"]')
        if title_el is None:
            continue
        href = title_el.get("href", "")
        if not item_id or not href:
            continue
        if item_id in seen_ids:
            continue
        seen_ids.add(item_id)

        specific_params_el = item.select_one(
            '[data-marker="item-specific-params"]'
        )
        specific_params = (
            specific_params_el.get_text(" ", strip=True)
            if specific_params_el
            else ""
        )
        location_el = item.select_one('[data-marker="item-location"]')
        price_el = item.select_one('[data-marker="item-price-value"]')

        jobs.append(
            Job(
                role=title_el.get_text(strip=True),
                company=_company_name(item),
                location=(
                    location_el.get_text(strip=True) if location_el else ""
                ),
                link=urljoin(AVITO_BASE_URL, str(href)),
                description=_description_snippet(item, specific_params),
                source="avito",
                external_id=str(item_id),
                salary=price_el.get_text(strip=True) if price_el else "",
                apply_method="avito_resume_apply",
            )
        )

    return jobs
