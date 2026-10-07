"""Все селекторы и тексты talanto.work в одном месте: вёрстка сайта
меняется, и при поломке править нужно только этот файл."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TalantoSelectors:
    base_url: str = "https://talanto.work"
    # Карточки в выдаче и ссылки внутри них ведут на /jobs/<uuid>.
    job_link: str = 'a[href^="/jobs/"]'
    job_path_regex: str = (
        r"^/jobs/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-"
        r"[0-9a-f]{12})$"
    )
    contacts_button_text: str = "Показать контакты"
    description_heading: str = "Описание вакансии"
    company_link: str = 'a[href^="/companies/"]'
    # Окно «Контакты» — ищем по фразе-подсказке внутри него.
    contacts_dialog_marker: str = "Нажмите на ссылку"
    # Ссылка «Apply <компания>» в окне контактов: переход через Talanto.
    apply_path: str = "/api/go/"


SELECTORS = TalantoSelectors()
