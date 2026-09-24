"""Рыночные данные из собранных вакансий: регион удалёнки, навыки,
которые требуют, и зарплаты. Всё без LLM — регулярками по тексту
вакансии, чтобы работало на тысячах записей бесплатно."""

from __future__ import annotations

import re
from collections import Counter
from statistics import median

# --- Регион удалёнки ---------------------------------------------------

# ponytail: только явные формулировки "нанимаем лишь из США/Европы";
# голое "Remote" — не ограничение. Если начнёт пропускать — добавить
# шаблоны сюда.
_US_ONLY_RE = re.compile(
    r"\b(us|u\.s\.|usa|united states)[- ]?(only|based)\b"
    r"|\bremote\s*[-–(]\s*(us|usa|united states)\b"
    r"|\b(located|based|reside|residing)\s+in\s+the\s+(us|u\.s\.|usa|united states)\b"
    r"|\b(authorized|authorization)\s+to\s+work\s+in\s+the\s+(us|u\.s\.|usa|united states)\b"
    r"|\bus\s+citizens?\b|\bgreen\s+card\b",
    re.IGNORECASE,
)
_EU_ONLY_RE = re.compile(
    r"\b(eu|europe|emea)[- ]?(only|based)\b"
    r"|\b(located|based|reside|residing)\s+in\s+(the\s+)?(eu|europe|european union)\b"
    r"|\beu\s+work\s+permit\b",
    re.IGNORECASE,
)
_GLOBAL_RE = re.compile(
    r"\b(anywhere|worldwide|work from anywhere|global(ly)?\s+remote|fully remote,? worldwide)\b",
    re.IGNORECASE,
)

REGION_LABELS = {
    "us_only": "🇺🇸 только США",
    "europe_only": "🇪🇺 только Европа",
    "global": "🌍 откуда угодно",
}


def remote_region(text: str) -> str | None:
    """us_only / europe_only / global или None — по локации+описанию."""
    if _US_ONLY_RE.search(text):
        return "us_only"
    if _EU_ONLY_RE.search(text):
        return "europe_only"
    if _GLOBAL_RE.search(text):
        return "global"
    return None


# --- Навыки ------------------------------------------------------------

_SKILL_PATTERNS: dict[str, str] = {
    "Python": r"\bpython\b",
    "Django": r"\bdjango\b",
    "FastAPI": r"\bfast\s?api\b",
    "Flask": r"\bflask\b",
    "asyncio": r"\basyncio\b|\baiohttp\b",
    "Celery": r"\bcelery\b",
    "SQLAlchemy": r"\bsqlalchemy\b",
    "PostgreSQL": r"\bpostgres(ql)?\b",
    "MySQL": r"\bmysql\b",
    "MongoDB": r"\bmongo(db)?\b",
    "Redis": r"\bredis\b",
    "ClickHouse": r"\bclickhouse\b",
    "Elasticsearch": r"\belastic(search)?\b",
    "Kafka": r"\bkafka\b",
    "RabbitMQ": r"\brabbit\s?mq\b",
    "Docker": r"\bdocker\b",
    "Kubernetes": r"\bkubernetes\b|\bk8s\b",
    "Terraform": r"\bterraform\b",
    "AWS": r"\baws\b|amazon web services",
    "GCP": r"\bgcp\b|google cloud",
    "Azure": r"\bazure\b",
    "Linux": r"\blinux\b",
    "CI/CD": r"\bci\s?/\s?cd\b|github actions|gitlab ci",
    "gRPC": r"\bgrpc\b",
    "GraphQL": r"\bgraphql\b",
    "Microservices": r"микросервис|\bmicroservices?\b",
    "pytest": r"\bpytest\b",
    "Pandas": r"\bpandas\b",
    "Airflow": r"\bairflow\b",
    "Spark": r"\bspark\b",
    "LLM": r"\bllms?\b|\bgpt\b|\blangchain\b|\bopenai\b",
    "ML": r"\bmachine learning\b|машинн\w+ обучени|\bpytorch\b|\btensorflow\b",
    "Go": r"\bgolang\b|\bGo\b",
    "Java": r"\bjava\b(?!script)",
    "TypeScript": r"\btypescript\b",
    "JavaScript": r"\bjavascript\b",
    "React": r"\breact\b",
    "Rust": r"\brust\b",
    "Prometheus/Grafana": r"\bprometheus\b|\bgrafana\b",
    "English": r"\benglish\b|английск",
}
_SKILL_RES = {
    name: re.compile(p, 0 if name == "Go" else re.IGNORECASE)
    for name, p in _SKILL_PATTERNS.items()
}


def extract_skills(text: str) -> list[str]:
    return [name for name, rx in _SKILL_RES.items() if rx.search(text)]


def skill_demand(entries: list[dict], resume_text: str) -> list[dict]:
    """Доля вакансий, где навык упомянут, и есть ли он в резюме —
    только по записям, где навыки уже извлечены (новые отклики)."""
    with_skills = [e for e in entries if "skills" in e]
    if not with_skills:
        return []
    counts = Counter(s for e in with_skills for s in e["skills"])
    have = set(extract_skills(resume_text))
    return [
        {
            "skill": skill,
            "count": count,
            "share": round(count / len(with_skills) * 100, 1),
            "in_resume": skill in have,
        }
        for skill, count in counts.most_common()
    ]


# --- Зарплаты ----------------------------------------------------------

_CURRENCIES = (
    ("RUB", re.compile(r"₽|руб|\brub\b", re.IGNORECASE)),
    ("USD", re.compile(r"\$|\busd\b", re.IGNORECASE)),
    ("EUR", re.compile(r"€|\beur\b", re.IGNORECASE)),
    ("INR", re.compile(r"\binr\b|₹", re.IGNORECASE)),
    ("KZT", re.compile(r"₸|\bkzt\b", re.IGNORECASE)),
    ("CAD", re.compile(r"\bcad\b", re.IGNORECASE)),
    ("GBP", re.compile(r"£|\bgbp\b", re.IGNORECASE)),
)
_YEARLY_RE = re.compile(r"year|/yr|\bгод|в год|annual", re.IGNORECASE)
_NUMBER_RE = re.compile(r"\d[\d\s,]*\d|\d")


def parse_salary(text: str) -> dict | None:
    """'180 000 — 250 000 ₽/мес' → {currency, min, max} в месяц.
    Одно число — и min, и max. None, если не разобрать."""
    if not text:
        return None
    clean = text.replace("\u200d", "").replace("\xa0", " ")
    currency = next((c for c, rx in _CURRENCIES if rx.search(clean)), None)
    numbers = [
        int(re.sub(r"[\s,]", "", n)) for n in _NUMBER_RE.findall(clean)
    ]
    numbers = [n for n in numbers if n >= 100]
    if not currency or not numbers:
        return None
    low, high = min(numbers), max(numbers)
    if _YEARLY_RE.search(clean):
        low, high = round(low / 12), round(high / 12)
    return {"currency": currency, "min": low, "max": high}


def salary_stats(entries: list[dict]) -> list[dict]:
    """Медианы "от"/"до" в месяц по каждой валюте по всем собранным
    вакансиям (не только откликам — это срез рынка)."""
    by_currency: dict[str, list[dict]] = {}
    for e in entries:
        parsed = parse_salary(e.get("salary") or "")
        if parsed:
            by_currency.setdefault(parsed["currency"], []).append(parsed)
    return sorted(
        (
            {
                "currency": currency,
                "count": len(items),
                "median_min": round(median(i["min"] for i in items)),
                "median_max": round(median(i["max"] for i in items)),
            }
            for currency, items in by_currency.items()
        ),
        key=lambda row: -row["count"],
    )
