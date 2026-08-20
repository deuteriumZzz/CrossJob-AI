import html
from typing import Optional

_COLUMNS = (
    "<th>Дата</th><th>Площадка</th><th>Компания</th><th>Сайт</th>"
    "<th>Вакансия</th><th>Зарплата</th><th>Статус</th><th>Балл</th>"
    "<th>Не хватает</th><th>Письмо</th>"
)


def render_applications_html(
    entries: list[dict],
    stats: dict,
    top_gaps: Optional[list[tuple[str, int]]] = None,
) -> str:
    top_gaps = top_gaps or []
    applications = [e for e in entries if e["status"] != "skipped_low_fit"]
    skipped = [e for e in entries if e["status"] == "skipped_low_fit"]
    rows = "\n".join(_row(e) for e in reversed(applications))
    skipped_section = ""
    if skipped:
        skipped_rows = "\n".join(_row(e) for e in reversed(skipped))
        skipped_section = f"""
<details>
<summary>{len(skipped)} пропущено из-за низкого балла</summary>
<table>
<thead><tr>{_COLUMNS}</tr></thead>
<tbody>
{skipped_rows}
</tbody>
</table>
</details>"""
    gaps_section = ""
    if top_gaps:
        gaps_items = "\n".join(
            f"<li>{html.escape(gap)} — {count}</li>" for gap, count in top_gaps
        )
        gaps_section = f"""
<div class="gaps">
<b>Чаще всего не хватает:</b>
<ul>{gaps_items}</ul>
</div>"""
    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>Отклики CrossJob-AI</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", Roboto, sans-serif;
    margin: 2rem; background: #0b0c10; color: #e8e8e8; }}
  h1 {{ font-size: 1.3rem; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ text-align: left; padding: 0.5rem 0.75rem;
    border-bottom: 1px solid #333; vertical-align: top; }}
  th {{ color: #99a3ad; font-weight: 600; }}
  a {{ color: #7ab8ff; }}
  .status-applied {{ color: #6fdc8c; }}
  .status-dry_run {{ color: #e0c05a; }}
  .status-skipped_low_fit {{ color: #d97a7a; }}
  details summary {{ cursor: pointer; color: #99a3ad; margin: 1rem 0; }}
  pre {{ white-space: pre-wrap; font-family: inherit; margin: 0.5rem 0 0; }}
  .count {{ color: #99a3ad; margin-bottom: 1rem; }}
  .stats {{ display: flex; gap: 1.5rem; margin-bottom: 1.5rem; }}
  .stats div {{ background: #16181d; border-radius: 8px;
    padding: 0.75rem 1rem; }}
  .stats b {{ font-size: 1.2rem; display: block; }}
  .gaps {{ background: #16181d; border-radius: 8px; padding: 0.75rem 1rem;
    margin-bottom: 1.5rem; }}
  .gaps ul {{ margin: 0.5rem 0 0; padding-left: 1.25rem; }}
</style>
</head>
<body>
<h1>Отклики CrossJob-AI</h1>
<div class="stats">
<div>Сегодня<b>{stats['day']}</b></div>
<div>За неделю<b>{stats['week']}</b></div>
<div>За месяц<b>{stats['month']}</b></div>
</div>
{gaps_section}
<div class="count">{len(applications)} записей, последние сверху</div>
<table>
<thead><tr>{_COLUMNS}</tr></thead>
<tbody>
{rows}
</tbody>
</table>
{skipped_section}
</body>
</html>
"""


def _row(e: dict) -> str:
    status_class = f"status-{html.escape(e['status'])}"
    cover_letter = html.escape(e["cover_letter"])
    link = html.escape(e["link"])
    title = html.escape(e["title"])
    salary = html.escape(e.get("salary") or "")
    company_url = e.get("company_url") or ""
    company_cell = (
        f'<a href="{html.escape(company_url)}" target="_blank" '
        'rel="noopener">сайт</a>'
        if company_url
        else ""
    )
    score = e.get("score")
    gaps = html.escape(", ".join(e.get("gaps") or []))
    return f"""<tr>
<td>{html.escape(e['applied_at'])}</td>
<td>{html.escape(e['source'])}</td>
<td>{html.escape(e['company'])}</td>
<td>{company_cell}</td>
<td><a href="{link}" target="_blank" rel="noopener">{title}</a></td>
<td>{salary}</td>
<td class="{status_class}">{html.escape(e['status'])}</td>
<td>{score if score is not None else ''}</td>
<td>{gaps}</td>
<td><details><summary>показать</summary><pre>{cover_letter}</pre></details></td>
</tr>"""
