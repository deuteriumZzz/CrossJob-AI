"""Единые фильтры поиска: пользователь задаёт формат работы и «только с
зарплатой» один раз («Что ищу»), а каждая площадка сама переводит их на
параметры своего сайта. Площадка, которая фильтра не умеет, его пропускает
(см. FILTER_SUPPORT — по нему же интерфейс показывает «не поддерживается»).
Свои настройки площадки (<source>.remote_only и т.п.) главнее общих."""

from __future__ import annotations

from datetime import date
from typing import Optional

FORMATS = ("remote", "hybrid", "onsite")
EMPLOYMENT = ("full", "part", "project", "internship")
PERIOD_DAYS = (1, 3, 7, 30)
LEVELS = ("intern", "junior", "middle", "senior", "lead")

# employment — тип занятости, period — «опубликовано за N дней».
# Что умеет каждая площадка. formats — формат работы, salary — «только с
# зарплатой», levels — уровень (junior/middle/...) на стороне сайта.
# Подтверждено по коду поиска каждой площадки; нет в списке — не разобрано.
FILTER_SUPPORT: dict[str, dict] = {
    "headhunter": {
        "formats": True,
        "salary": True,
        "levels": True,
        "employment": True,
        "period": True,
    },
    "linkedin": {
        "formats": True,
        "salary": False,
        "levels": True,
        "employment": True,
        "period": True,
    },
    "getmatch": {
        "formats": True,
        "salary": False,
        "levels": True,
        "period": True,
    },
    "habr_career": {
        "formats": "remote",
        "salary": True,
        "levels": True,
        "employment": "single",
        "period": True,
    },
    "avito": {
        "formats": "remote",
        "salary": False,
        "levels": True,
        "employment": "single",
        "period": False,
    },
    # Djinni принимает один employment (при двух сразу берёт remote) —
    # фильтр ставим, только если выбран ровно один формат.
    # Стаж у Djinni — exp_level (повторяемый, проверено вживую); «только с
    # зарплатой» у сайта нет, поэтому её отсеиваем по самой вакансии.
    "djinni": {
        "formats": "single",
        "salary": True,
        "levels": True,
        "employment": "single",
        "period": True,
    },
    # GeekJob: rm=1 — удалённо, ih=1 — офис (inhouse), s=1&money — только с
    # зарплатой; своего «гибрида» и уровней нет.
    "geekjob": {
        "formats": "single",
        "salary": True,
        "levels": False,
        "employment": "single",
        "period": False,
    },
    # Wellfound ищет по /role/r/<роль> — это страница удалённых вакансий
    # (/role/l/... — по городам), Himalayas целиком удалённая: формат
    # «удалённо» у них уже есть сам по себе, остальных фильтров нет.
    "wellfound": {"formats": "remote", "salary": False, "levels": False},
    "himalayas": {
        "formats": "remote",
        "salary": True,
        "levels": True,
        "employment": True,
        "period": False,
    },
    # Hirify: формат (удалёнка / офис), тип занятости и период — по данным
    # самой вакансии; уровня и «только с зарплатой» в открытых данных нет.
    "hirify": {
        "formats": True,
        "salary": False,
        "levels": False,
        "employment": True,
        "period": True,
    },
    "talanto": {
        "formats": True,
        "salary": True,
        "levels": True,
        "employment": True,
        "period": True,
    },
}

# LinkedIn f_WT: 1 — на месте, 2 — удалённо, 3 — гибрид.
_LINKEDIN_WORK_TYPE = {"onsite": "1", "remote": "2", "hybrid": "3"}


def work_formats(preferences: dict) -> list[str]:
    """Включённые общие форматы работы ("Что ищу" → «Формат работы»)."""
    return [f for f in FORMATS if preferences.get(f)]


def employment_types(preferences: dict) -> list[str]:
    """Выбранные типы занятости («Что ищу»): пусто — любой."""
    chosen = preferences.get("employment_types") or []
    return [e for e in EMPLOYMENT if e in chosen]


def posted_within_days(preferences: dict) -> int:
    """«Опубликовано за N дней» (1, 3, 7 или 30); 0 — без ограничения."""
    try:
        days = int(preferences.get("posted_within_days") or 0)
    except (TypeError, ValueError):
        return 0
    return days if days in PERIOD_DAYS else 0


_RU_MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5,
    "июня": 6, "июля": 7, "августа": 8, "сентября": 9, "октября": 10,
    "ноября": 11, "декабря": 12,
}  # fmt: skip


def parse_ru_date(text: str, today: Optional["date"] = None) -> str:
    """«24 сентября» / «сегодня» / «вчера» → ISO-дата ('' если не
    разобрали). Года на карточке нет: берём текущий, а если дата вышла бы в
    будущем — прошлый."""
    from datetime import date as _date
    from datetime import timedelta

    today = today or _date.today()
    word = (text or "").strip().lower()
    if word == "сегодня":
        return today.isoformat()
    if word == "вчера":
        return (today - timedelta(days=1)).isoformat()
    parts = word.split()
    if len(parts) >= 2 and parts[0].isdigit() and parts[1] in _RU_MONTHS:
        try:
            day = _date(today.year, _RU_MONTHS[parts[1]], int(parts[0]))
        except ValueError:
            return ""
        if day > today:
            day = day.replace(year=today.year - 1)
        return day.isoformat()
    return ""


def posted_too_old(posted_at: str, preferences: dict) -> bool:
    """True, если вакансия опубликована раньше выбранного периода.
    Площадкам без своего фильтра по дате (Djinni, Habr) период применяем по
    дате самой вакансии; неизвестная дата — не отсекаем."""
    days = posted_within_days(preferences)
    if not days or not posted_at:
        return False
    from datetime import datetime, timedelta

    try:
        # Python 3.9 не читает «Z» на конце — заменяем на +00:00.
        posted = datetime.fromisoformat(
            posted_at[:-1] + "+00:00" if posted_at.endswith("Z") else posted_at
        )
    except ValueError:
        return False
    now = datetime.now(posted.tzinfo) if posted.tzinfo else datetime.now()
    return now - posted > timedelta(days=days)


def single_employment(preferences: dict) -> Optional[str]:
    """full_time или part_time для площадок с одним значением занятости
    (Habr, Avito, GeekJob): ставится, только если выбрана ровно одна из
    «полная» / «частичная»."""
    chosen = [
        e for e in employment_types(preferences) if e in ("full", "part")
    ]
    if len(chosen) != 1:
        return None
    return "full_time" if chosen[0] == "full" else "part_time"


_HH_EMPLOYMENT = {"full": "FULL", "part": "PART", "project": "PROJECT"}


def hh_employment(preferences: dict) -> tuple[list[str], bool]:
    """(employment_form повторяемый, internship) для HH."""
    chosen = employment_types(preferences)
    return (
        [_HH_EMPLOYMENT[e] for e in chosen if e in _HH_EMPLOYMENT],
        "internship" in chosen,
    )


# LinkedIn f_JT: F полная, P частичная, C контракт, T временная, I стажировка.
_LINKEDIN_JOB_TYPE = {
    "full": "F",
    "part": "P",
    "project": "C",
    "internship": "I",
}
# f_TPR: секунды; «3 дня» округляем до недели (у LinkedIn нет 3 дней).
_LINKEDIN_PERIOD = {1: "r86400", 3: "r604800", 7: "r604800", 30: "r2592000"}


def levels(preferences: dict) -> list[str]:
    """Выбранные уровни («Что ищу»): пусто — любой, фильтр не ставится."""
    chosen = preferences.get("levels") or []
    return [level for level in LEVELS if level in chosen]


# HH: опыт задаётся стажем, а не грейдом (experience=…, повторяемый).
_HH_EXPERIENCE = {
    "intern": ["noExperience"],
    "junior": ["noExperience", "between1And3"],
    "middle": ["between1And3", "between3And6"],
    "senior": ["between3And6", "moreThan6"],
    "lead": ["moreThan6"],
}
# LinkedIn f_E: 1 стажёр, 2 начальный, 3 ассоциированный, 4 средний-старший,
# 5 директор, 6 топ.
_LINKEDIN_EXPERIENCE = {
    "intern": ["1"],
    "junior": ["2"],
    "middle": ["3", "4"],
    "senior": ["4"],
    "lead": ["5", "6"],
}
# GetMatch se= и Talanto levels= (у Talanto «middle» называется «mid»).
_GETMATCH_SENIORITY = {
    "junior": "junior",
    "middle": "middle",
    "senior": "senior",
    "lead": "lead",
}
_TALANTO_LEVELS = {
    "junior": "junior",
    "middle": "mid",
    "senior": "senior",
    "lead": "lead",
}


# Djinni exp_level — стаж в годах, повторяемый (проверено вживую
# 2026-10-07: 1y — 1 стр., 2y — 2 стр., оба вместе — 3 стр.).
_DJINNI_EXPERIENCE = {
    "intern": ["no_exp"],
    "junior": ["no_exp", "1y", "2y"],
    "middle": ["3y", "4y", "5y"],
    "senior": ["5y", "6y", "7y", "8y", "9y", "10y"],
    "lead": ["6y", "7y", "8y", "9y", "10y"],
}


def _mapped(table: dict, chosen: list[str]) -> list[str]:
    out: list[str] = []
    for level in chosen:
        for value in (
            table.get(level, [])
            if isinstance(table.get(level), list)
            else [table.get(level)]
        ):
            if value and value not in out:
                out.append(value)
    return out


def hh_experience(preferences: dict) -> list[str]:
    return _mapped(_HH_EXPERIENCE, levels(preferences))


def getmatch_seniority(preferences: dict) -> list[str]:
    return _mapped(_GETMATCH_SENIORITY, levels(preferences))


def talanto_levels(preferences: dict) -> list[str]:
    return _mapped(_TALANTO_LEVELS, levels(preferences))


def habr_qualifications(preferences: dict) -> list[str]:
    """Названия квалификаций Habr (одно значение за запрос — вызывающий код
    ищет по каждому). Стажёр и остальные совпадают с QUALIFICATION_IDS."""
    return levels(preferences)


def skip_remote_only_platform(preferences: dict) -> bool:
    """Площадки, где все вакансии удалённые (Wellfound, Himalayas), нечего
    делать тем, кто ищет только офис или гибрид: формат выбран, а
    «удалённо» среди него нет."""
    formats = work_formats(preferences)
    return bool(formats) and "remote" not in formats


# GetMatch l= (проверено вживую 2026-10-08 по чекбоксам и адресу): remote —
# «Удалённо»; «офис или гибрид» — moscow, saints_p, regions_ru, relocate.
_GETMATCH_OFFICE_PLACES = ["moscow", "saints_p", "regions_ru", "relocate"]
_GETMATCH_PERIOD = {1: "1d", 3: "3d", 7: "7d", 30: "30d"}


def getmatch_locations(preferences: dict) -> list[str]:
    """l= GetMatch из общих форматов. Офис и гибрид у сайта — один пункт
    «Офис или гибрид в …» (по городам), поэтому они идут вместе. Все
    форматы выбраны или ни одного — без фильтра."""
    formats = work_formats(preferences)
    places: list[str] = []
    if "remote" in formats:
        places.append("remote")
    if "hybrid" in formats or "onsite" in formats:
        places += _GETMATCH_OFFICE_PLACES
    if len(places) == 1 + len(_GETMATCH_OFFICE_PLACES):
        return []
    return places


def getmatch_period(preferences: dict) -> str:
    return _GETMATCH_PERIOD.get(posted_within_days(preferences), "")


def avito_click_format(preferences: dict) -> str:
    """Формат Avito, который ставится кликом по радио «Формат работы» (на
    сайте один выбор): office или hybrid, если выбран ровно он один.
    Удалённо идёт через адрес (см. remote_only), остальное — без фильтра.
    Проверено вживую 2026-10-08: «В офисе» — 84 из 89 по «python»;
    клик «Гибрид» выдачу не изменил (в этой выдаче гибридных нет или
    маркер не срабатывает) — не подтверждено."""
    formats = work_formats(preferences)
    if formats == ["onsite"]:
        return "office"
    if formats == ["hybrid"]:
        return "hybrid"
    return ""


def remote_only(preferences: dict, source: str) -> bool:
    """«Только удалённые» для площадок, у которых фильтр двоичный. Общий
    выбор из «Что ищу» главнее: пока в нём включён хоть один формат, один
    тумблер управляет всеми площадками (включён только «Удалённо» — только
    удалённые, иначе фильтра нет). Свой remote_only площадки действует,
    лишь если общие форматы не выбраны вовсе."""
    formats = work_formats(preferences)
    if formats:
        return formats == ["remote"]
    return bool((preferences.get(source) or {}).get("remote_only"))


def linkedin_search_params(preferences: dict) -> dict:
    """f_WT и сортировка LinkedIn из общих форматов; пока ни один не выбран —
    формат не ограничивается (любой). f_AL (только Easy Apply) не
    настраивается: бот умеет откликаться лишь так."""
    formats = work_formats(preferences)
    # Без sortBy=DD: по релевантности, как до 7.10 (по дате шла нерелевантная
    # выдача; свежесть даёт пропуск просмотренных вакансий).
    params = {"f_AL": "true"}
    if formats:
        params["f_WT"] = ",".join(
            sorted(_LINKEDIN_WORK_TYPE[f] for f in formats)
        )
    experience = _mapped(_LINKEDIN_EXPERIENCE, levels(preferences))
    if experience:
        params["f_E"] = ",".join(sorted(experience))
    job_types = [_LINKEDIN_JOB_TYPE[e] for e in employment_types(preferences)]
    if job_types:
        params["f_JT"] = ",".join(sorted(job_types))
    days = posted_within_days(preferences)
    if days:
        params["f_TPR"] = _LINKEDIN_PERIOD[days]
    return params


def djinni_experience(preferences: dict) -> list[str]:
    return _mapped(_DJINNI_EXPERIENCE, levels(preferences))


def talanto_salary_params(preferences: dict) -> str:
    """«Только с зарплатой» у Talanto: salary_min=1 оставляет только
    вакансии с указанной зарплатой (проверено вживую 2026-10-07: без
    фильтра 16 из 35 «зарплата не указана», с ним — 0)."""
    if preferences.get("only_with_salary"):
        return "&salary_min=1&salary_input_currency=USD"
    return ""


# Talanto work_types (повторяемый) и period (проверено вживую 2026-10-08:
# «python»: full 465, part 10, оба вместе 475; период — сутки 14, три дня
# 59, неделя 161, месяц 671). part_time и internship сайт не знает.
_TALANTO_WORK_TYPES = {
    "full": "full",
    "part": "part",
    "project": "contract",
    "internship": "intern",
}
_TALANTO_PERIOD = {1: "day", 3: "three_days", 7: "week", 30: "month"}


def talanto_extra_query(preferences: dict) -> str:
    """Хвост адреса Talanto: зарплата, тип занятости и период."""
    query = talanto_salary_params(preferences)
    for kind in employment_types(preferences):
        query += f"&work_types={_TALANTO_WORK_TYPES[kind]}"
    days = posted_within_days(preferences)
    if days:
        query += f"&period={_TALANTO_PERIOD[days]}"
    return query


# Himalayas (проверено вживую 2026-10-08 в вашем окне бота): type= и
# experience= — списки через запятую; salary-required=true — «только с
# зарплатой». Сайт целиком удалённый, формат и период не нужны.
_HIMALAYAS_TYPE = {
    "full": "full-time",
    "part": "part-time",
    "project": "contractor",
    "internship": "intern",
}
_HIMALAYAS_EXPERIENCE = {
    "intern": ["entry-level"],
    "junior": ["entry-level"],
    "middle": ["mid-level"],
    "senior": ["senior"],
    "lead": ["manager"],
}


def himalayas_query(preferences: dict) -> str:
    """Хвост адреса Himalayas: тип работы, уровень, «только с зарплатой»."""
    query = ""
    types = [_HIMALAYAS_TYPE[e] for e in employment_types(preferences)]
    if types:
        query += "&type=" + ",".join(types)
    experience = _mapped(_HIMALAYAS_EXPERIENCE, levels(preferences))
    if experience:
        query += "&experience=" + ",".join(experience)
    if preferences.get("only_with_salary"):
        query += "&salary-required=true"
    return query


def djinni_employment(preferences: dict) -> Optional[str]:
    """employment у Djinni: remote или office (офис, в том числе гибрид).
    Проверено на сайте: employment=remote — удалённые, office — почти
    без удалённых; два значения сразу дают только удалённые, поэтому
    ставим фильтр лишь при одном выбранном формате."""
    formats = work_formats(preferences)
    if formats == ["remote"]:
        return "remote"
    if formats in (["onsite"], ["hybrid"]):
        return "office"
    # Формат не выбран — параметр свободен для «частичной занятости».
    if not formats and single_employment(preferences) == "part_time":
        return "parttime"
    return None


def geekjob_search_params(preferences: dict) -> dict:
    """Параметры /vacancies и /json/find/vacancy у GeekJob (проверено
    вживую 2026-10-07: python — 43 вакансии, rm=1 — 37, ih=1 — 22,
    s=1&money=120000 — 16). Сортировка sort=1 работает только в JSON-запросе,
    страница её из адреса не читает — поэтому её здесь нет. Формат ставится
    при одном выбранном (удалённо или офис), «гибрида» на сайте нет."""
    params: dict = {}
    if single_employment(preferences) == "part_time":
        params["pt"] = "1"
    formats = work_formats(preferences)
    if formats == ["remote"]:
        params["rm"] = "1"
    elif formats == ["onsite"]:
        params["ih"] = "1"
    if preferences.get("only_with_salary"):
        params["s"] = "1"
        params["money"] = "10000"  # нижняя граница ползунка — «любая»
    return params


# Talanto work_formats: remote, hybrid, office (проверено кликами).
_TALANTO_FORMAT = {"remote": "remote", "hybrid": "hybrid", "onsite": "office"}


def talanto_work_formats(preferences: dict) -> list[str]:
    return [_TALANTO_FORMAT[f] for f in work_formats(preferences)]


def support_matrix() -> dict[str, dict]:
    return FILTER_SUPPORT


def supports(source: str, name: str) -> Optional[bool | str]:
    return FILTER_SUPPORT.get(source, {}).get(name)
