import re
from typing import Optional

from src.job import Job
from src.job_sources.market_stats import remote_region
from src.job_sources.preferences import effective_list
from src.logging import logger

# Признаки сомнительных вакансий («лёгкий заработок», ввод данных на дому и
# т.п.) — живой случай 2026-10-07: «Ewped. Без опыта. Обработка и сортировка
# данных» получила 9/10 от LLM (за час до этого — 1/10), и на неё ушёл
# отклик. Оценке LLM тут доверять нельзя, поэтому — жёсткий фильтр до неё.
# Только сильные сигналы: «без опыта» само по себе законно у junior-ролей.
_SUSPICIOUS_PHRASES = (
    "лёгкий заработок",
    "легкий заработок",
    "быстрый заработок",
    "лёгкие деньги",
    "легкие деньги",
    "ежедневная оплата",
    "ежедневные выплаты",
    "оплата ежедневно",
    "выплаты ежедневно",
    "оплата каждый день",
    "выплаты каждый день",
    "без вложений",
    "работа на дому",
    "подработка на дому",
    "обработка и сортировка данных",
    "заполнение анкет",
    "набор текста на дому",
    "оператор ввода данных",
    "easy money",
    "quick cash",
    "make money online",
    "data entry from home",
    "work from home and earn",
)
_SUSPICIOUS_INCOME_RE = re.compile(
    r"(доход|заработок|зарплата|earn)\s*(от\s*)?\$?\d[\d\s,.]*\s*"
    r"(₽|руб|р\.|usd|\$|€)?\s*(в|/|per|a)\s*(день|сутки|час|day|hour)",
    re.IGNORECASE,
)


def suspicious_reason(job: Job, preferences: dict) -> Optional[str]:
    """Что именно в вакансии выглядит как «лёгкие деньги»/мошенничество, или
    None. Отключается suspicious_filter: false; свои фразы —
    suspicious_phrases: [...] в work_preferences.yaml."""
    if not preferences.get("suspicious_filter", True):
        return None
    text = f"{job.role}\n{job.description}".lower()
    phrases = _SUSPICIOUS_PHRASES + tuple(
        p.lower() for p in preferences.get("suspicious_phrases") or []
    )
    for phrase in phrases:
        if phrase in text:
            return phrase
    match = _SUSPICIOUS_INCOME_RE.search(text)
    return match.group(0) if match else None


# ponytail: подстрочный маркер "удал" вместо точного списка меток —
# сейчас единственный источник, реально размечающий remote в job.location,
# это habr_career (см. REMOTE_LABEL = "Можно удалённо" в habr_career/
# mapping.py), но проверка обобщена на любой источник/язык разметки
# ("remote"), а не привязана к его точной строке — если появится ещё
# один источник с remote-меткой, дублировать этот бай-пас не придётся.
_REMOTE_MARKERS = ("удал", "remote")


def passes_blacklists(job: Job, preferences: dict) -> bool:
    def matches_any(value: str, blacklist: list) -> bool:
        value_lower = value.lower()
        return any(bad.lower() in value_lower for bad in blacklist)

    def is_remote(location: str) -> bool:
        location_lower = location.lower()
        return any(marker in location_lower for marker in _REMOTE_MARKERS)

    if matches_any(job.company, preferences.get("company_blacklist", [])):
        return False
    reason = suspicious_reason(job, preferences)
    if reason:
        logger.info(
            f"Сомнительная вакансия, пропускаю: {job.role!r} ({reason!r})"
        )
        return False
    title_blacklist = preferences.get("title_blacklist", [])
    # Не только заголовок — некоторые нежелательные вакансии (военные
    # контракты и т.п.) не называют это прямо в title, слово всплывает
    # только в тексте описания. Одинаково работает для RU/EN: обычное
    # совпадение подстроки, без учёта регистра, языку всё равно.
    if matches_any(job.role, title_blacklist) or matches_any(
        job.description, title_blacklist
    ):
        return False
    if matches_any(job.location, preferences.get("location_blacklist", [])):
        return False
    # Удалёнка "только из США" и т.п. — по умолчанию отсекается us_only,
    # иначе отклики уходят туда, где кандидата не возьмут по географии.
    # excluded_remote_regions: [] — ничего не отсекать.
    excluded = preferences.get("excluded_remote_regions", ["us_only"])
    if (
        excluded
        and remote_region(f"{job.location}\n{job.description}") in excluded
    ):
        return False

    # locations — общий allowlist для площадок, которые ищут широко
    # (например HH — по всей area=113 "Россия") и полагаются на этот
    # пост-фильтр, чтобы сузить до конкретных городов вроде "Москва".
    # Исключения — площадки, где job.location никогда не заполняется:
    # LinkedIn (фильтрует по локации на уровне самого поиска —
    # linkedin.locations/geoId в search.py, см. search_easy_apply_
    # jobs), himalayas (карточки поиска не подтверждены вживую —
    # анти-бот интерстишл, см. docstring search_jobs) и telegram
    # (посты — свободный текст, структурного поля локации в принципе
    # нет). Для любой из них allowlist проверял бы пустую строку против
    # списка городов и отбрасывал вообще ВСЕ вакансии до единой
    # (подтверждено живьём на LinkedIn: "Found 0 matching" при том, что
    # напрямую тот же поиск находил вакансии) — не рискуем тем же
    # багом на остальных.
    # habr_career теперь размечает location (см. _extract_location в
    # habr_career/mapping.py) — участвует в allowlist на общих
    # основаниях, но remote-вакансии ("Можно удалённо") проходят
    # независимо от списка городов, а не только вакансии в этих
    # городах — пользователь ищет удалёнку + свои города, а не только
    # свои города.
    if job.source not in ("linkedin", "himalayas", "telegram"):
        locations = effective_list(preferences, job.source, "locations")
        if (
            locations
            and not is_remote(job.location)
            and not matches_any(job.location, locations)
        ):
            return False

    return True
