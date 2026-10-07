"""Единые фильтры поиска: пользователь задаёт формат работы и «только с
зарплатой» один раз («Что ищу»), а каждая площадка сама переводит их на
параметры своего сайта. Площадка, которая фильтра не умеет, его пропускает
(см. FILTER_SUPPORT — по нему же интерфейс показывает «не поддерживается»).
Свои настройки площадки (<source>.remote_only и т.п.) главнее общих."""

from __future__ import annotations

from typing import Optional

FORMATS = ("remote", "hybrid", "onsite")
LEVELS = ("intern", "junior", "middle", "senior", "lead")

# Что умеет каждая площадка. formats — формат работы, salary — «только с
# зарплатой», levels — уровень (junior/middle/...) на стороне сайта.
# Подтверждено по коду поиска каждой площадки; нет в списке — не разобрано.
FILTER_SUPPORT: dict[str, dict] = {
    "headhunter": {"formats": True, "salary": True, "levels": True},
    "linkedin": {"formats": True, "salary": False, "levels": True},
    "getmatch": {"formats": "remote", "salary": False, "levels": True},
    "habr_career": {"formats": "remote", "salary": False, "levels": True},
    "avito": {"formats": "remote", "salary": False, "levels": True},
    # Djinni принимает один employment (при двух сразу берёт remote) —
    # фильтр ставим, только если выбран ровно один формат.
    "djinni": {"formats": "single", "salary": False, "levels": False},
    # GeekJob: rm=1 — удалённо, ih=1 — офис (inhouse), s=1&money — только с
    # зарплатой; своего «гибрида» и уровней нет.
    "geekjob": {"formats": "single", "salary": True, "levels": False},
    # Wellfound ищет по /role/r/<роль> — это страница удалённых вакансий
    # (/role/l/... — по городам), Himalayas целиком удалённая: формат
    # «удалённо» у них уже есть сам по себе, остальных фильтров нет.
    "wellfound": {"formats": "remote", "salary": False, "levels": False},
    "himalayas": {"formats": "remote", "salary": False, "levels": False},
    "talanto": {"formats": True, "salary": False, "levels": True},
}

# LinkedIn f_WT: 1 — на месте, 2 — удалённо, 3 — гибрид.
_LINKEDIN_WORK_TYPE = {"onsite": "1", "remote": "2", "hybrid": "3"}


def work_formats(preferences: dict) -> list[str]:
    """Включённые общие форматы работы ("Что ищу" → «Формат работы»)."""
    return [f for f in FORMATS if preferences.get(f)]


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
    как раньше, только удалённые. f_AL (только Easy Apply) не
    настраивается: бот умеет откликаться лишь так."""
    formats = work_formats(preferences) or ["remote"]
    params = {
        "f_AL": "true",
        "f_WT": ",".join(sorted(_LINKEDIN_WORK_TYPE[f] for f in formats)),
        "sortBy": "DD",
    }
    experience = _mapped(_LINKEDIN_EXPERIENCE, levels(preferences))
    if experience:
        params["f_E"] = ",".join(sorted(experience))
    return params


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
    return None


def geekjob_search_params(preferences: dict) -> dict:
    """Параметры /vacancies и /json/find/vacancy у GeekJob (проверено
    вживую 2026-10-07: python — 43 вакансии, rm=1 — 37, ih=1 — 22,
    s=1&money=120000 — 16). Сортировка sort=1 работает только в JSON-запросе,
    страница её из адреса не читает — поэтому её здесь нет. Формат ставится
    при одном выбранном (удалённо или офис), «гибрида» на сайте нет."""
    params: dict = {}
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
