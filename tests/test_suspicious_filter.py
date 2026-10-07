from src.job import Job
from src.job_sources.blacklist_filter import (
    passes_blacklists,
    suspicious_reason,
)


def _job(role: str, description: str = "") -> Job:
    return Job(
        role=role, company="Acme", description=description, source="geekjob"
    )


def test_scam_like_vacancy_is_filtered():
    job = _job("Ewped. Без опыта. Обработка и сортировка данных")
    assert suspicious_reason(job, {}) == "обработка и сортировка данных"
    assert not passes_blacklists(job, {})


def test_income_per_day_pattern():
    job = _job("Менеджер", "Доход от 5000 руб в день, оплата ежедневно")
    assert suspicious_reason(job, {})


def test_normal_junior_vacancy_passes():
    job = _job(
        "Junior Python Developer",
        "Без опыта коммерческой работы, но с pet-проектами. "
        "Оплата два раза в месяц.",
    )
    assert suspicious_reason(job, {}) is None
    assert passes_blacklists(job, {})


def test_filter_can_be_disabled_and_extended():
    job = _job("Лёгкий заработок")
    assert passes_blacklists(job, {"suspicious_filter": False})
    assert suspicious_reason(
        _job("Крипто-сигналы"), {"suspicious_phrases": ["крипто-сигналы"]}
    )
