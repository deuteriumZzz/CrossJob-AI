import html


def render_applications_html(entries: list[dict], stats: dict) -> str:
    rows = "\n".join(_row(e) for e in reversed(entries))
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
  details summary {{ cursor: pointer; color: #99a3ad; }}
  pre {{ white-space: pre-wrap; font-family: inherit; margin: 0.5rem 0 0; }}
  .count {{ color: #99a3ad; margin-bottom: 1rem; }}
  .stats {{ display: flex; gap: 1.5rem; margin-bottom: 1.5rem; }}
  .stats div {{ background: #16181d; border-radius: 8px;
    padding: 0.75rem 1rem; }}
  .stats b {{ font-size: 1.2rem; display: block; }}
</style>
</head>
<body>
<h1>Отклики CrossJob-AI</h1>
<div class="stats">
<div>Сегодня<b>{stats['day']}</b></div>
<div>За неделю<b>{stats['week']}</b></div>
<div>За месяц<b>{stats['month']}</b></div>
</div>
<div class="count">{len(entries)} записей, последние сверху</div>
<table>
<thead><tr><th>Дата</th><th>Площадка</th><th>Компания</th><th>Сайт</th><th>Вакансия</th><th>Зарплата</th><th>Статус</th><th>Письмо</th></tr></thead>
<tbody>
{rows}
</tbody>
</table>
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
    return f"""<tr>
<td>{html.escape(e['applied_at'])}</td>
<td>{html.escape(e['source'])}</td>
<td>{html.escape(e['company'])}</td>
<td>{company_cell}</td>
<td><a href="{link}" target="_blank" rel="noopener">{title}</a></td>
<td>{salary}</td>
<td class="{status_class}">{html.escape(e['status'])}</td>
<td><details><summary>показать</summary><pre>{cover_letter}</pre></details></td>
</tr>"""
