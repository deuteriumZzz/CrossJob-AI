from src.job import Job
from src.job_sources.html_text import strip_html


def _format_salary(raw: dict) -> str:
    lo, hi = raw.get("payment_from"), raw.get("payment_to")
    currency = raw.get("currency") or ""
    if lo and hi:
        return f"{lo}-{hi} {currency}".strip()
    if lo:
        return f"от {lo} {currency}".strip()
    if hi:
        return f"до {hi} {currency}".strip()
    return ""


def sj_vacancy_to_job(raw: dict) -> Job:
    """Преобразует ответ GET /vacancies/{id}/ от api.superjob.ru в Job.
    Названия полей проверены по официальному PHP-клиенту
    (github.com/superjobru/superjob-api-client) и документации API.
    Поля company_url нет: ответ SuperJob раскрывает только ссылки на
    профиль superjob.ru, а не на реальный внешний сайт работодателя —
    оставлено пустым, а не угадано."""
    return Job(
        role=raw.get("profession", ""),
        company=raw.get("firm_name", ""),
        location=(raw.get("town") or {}).get("title", ""),
        link=raw.get("link", ""),
        description=strip_html(raw.get("candidat", "") or raw.get("work", "")),
        source="superjob",
        external_id=str(raw.get("id", "")),
        salary=_format_salary(raw),
        apply_method="superjob_api",
    )
