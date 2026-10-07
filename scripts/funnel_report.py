"""Отчёт по воронке откликов.

Запуск: python scripts/funnel_report.py [папка output] [дней].

Читает applied_log.json, .run_history.jsonl и easy_apply_failures.jsonl —
показывает, где теряются отклики: по площадкам и дням, длительность
ходов и причины сбоев Easy Apply LinkedIn."""

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

output = Path(sys.argv[1] if len(sys.argv) > 1 else "data_folder/output")
days = int(sys.argv[2]) if len(sys.argv) > 2 else 14
since = (datetime.now() - timedelta(days=days)).date().isoformat()


def jsonl(name: str) -> list[dict]:
    path = output / name
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            pass
    return rows


apps = json.loads((output / "applied_log.json").read_text(encoding="utf-8"))[
    "applications"
]

print(f"=== Статусы по площадкам, за последние {days} дн. ===")
by_source: dict = defaultdict(Counter)
for e in apps:
    if e.get("applied_at", "")[:10] >= since:
        by_source[e["source"]][e["status"]] += 1
for source, counts in sorted(by_source.items()):
    line = ", ".join(f"{k}={v}" for k, v in counts.most_common())
    done, failed = counts["applied"], counts["skipped_easy_apply_failed"]
    rate = f" (сбоев формы {failed / (done + failed):.0%})" if failed else ""
    print(f"{source:12} {line}{rate}")

print("\n=== Отклики по дням ===")
per_day: dict = defaultdict(Counter)
for e in apps:
    day = e.get("applied_at", "")[:10]
    if day >= since and e["status"] == "applied":
        per_day[day][e["source"]] += 1
for day in sorted(per_day):
    print(day, dict(per_day[day]))

print("\n=== Длительность ходов (из .run_history.jsonl) ===")
durations: dict = defaultdict(list)
for row in jsonl(".run_history.jsonl"):
    durations[row["source"]].append(row["duration_seconds"])
if not durations:
    print("истории пока нет — накопится после следующих прогонов")
for source, values in sorted(durations.items()):
    print(
        f"{source:20} ходов={len(values)} среднее="
        f"{sum(values) / len(values) / 60:.1f} мин максимум="
        f"{max(values) / 60:.1f} мин"
    )

print("\n=== Причины сбоев Easy Apply (easy_apply_failures.jsonl) ===")
failures = jsonl("easy_apply_failures.jsonl")
if not failures:
    print("записей пока нет — накопятся после следующих прогонов LinkedIn")
for (reason, step), n in Counter(
    (f["reason"], f["step"]) for f in failures
).most_common():
    print(f"{n:4} {reason} (шаг {step})")
fields = Counter(
    tuple(field)[1][:60] for f in failures for field in f.get("fields", [])
)
if fields:
    print("поля на шагах со сбоем:")
    for text, n in fields.most_common(10):
        print(f"{n:4} {text}")
errors = Counter(err[:80] for f in failures for err in f.get("errors", []))
if errors:
    print("ошибки валидации на странице:")
    for text, n in errors.most_common(10):
        print(f"{n:4} {text}")
