"""Открытые доски удалённых вакансий без входа и без оплаты:
We Work Remotely (RSS, кнопка Apply ведёт прямо к работодателю —
проверено 2026-09-23) и ежемесячная ветка Hacker News «Who is hiring»
(в постах часто прямой email основателя/CTO).
RemoteOK/Remotive сюда не входят: отклик у первого за платной
подпиской, у второго страница вакансии за Cloudflare."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from html import unescape

import httpx

from src.direct.ats import _strip_html
from src.job import Job

TIMEOUT = 20
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; CrossJob-AI)"}

WWR_FEEDS = (
    "https://weworkremotely.com/categories/remote-back-end-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss",
)
HN_SEARCH_URL = (
    "https://hn.algolia.com/api/v1/search_by_date"
    "?tags=story,author_whoishiring&query=who%20is%20hiring&hitsPerPage=5"
)
HN_ITEM_URL = "https://hn.algolia.com/api/v1/items/{id}"


def _get(url: str) -> httpx.Response:
    response = httpx.get(
        url, timeout=TIMEOUT, headers=_HEADERS, follow_redirects=True
    )
    response.raise_for_status()
    return response


def parse_wwr_rss(xml_text: str) -> list[Job]:
    jobs = []
    for item in ET.fromstring(xml_text).iter("item"):
        title = item.findtext("title") or ""
        company, _, role = title.partition(": ")
        link = item.findtext("link") or ""
        jobs.append(
            Job(
                role=role or title,
                company=company if role else "",
                location=item.findtext("region") or "",
                link=link,
                description=_strip_html(item.findtext("description") or ""),
                source="direct",
                external_id=f"wwr-{link.rstrip('/').rsplit('/', 1)[-1]}",
            )
        )
    return jobs


def fetch_wwr() -> list[Job]:
    jobs: dict[str, Job] = {}
    for feed in WWR_FEEDS:
        for job in parse_wwr_rss(_get(feed).text):
            jobs[job.external_id] = job
    return list(jobs.values())


def parse_hn_comment(comment: dict) -> Job | None:
    """Первая строка поста по правилам ветки: "Компания | Роль |
    Локация | ...". Посты не по формату пропускаем."""
    html = comment.get("text") or ""
    if not html:
        return None
    first_line = unescape(re.split(r"<p>|\n", html, maxsplit=1)[0])
    parts = [p.strip() for p in _strip_html(first_line).split("|")]
    if len(parts) < 2:
        return None
    return Job(
        company=parts[0][:80],
        role=parts[1][:120],
        location=" | ".join(parts[2:4]),
        link=f"https://news.ycombinator.com/item?id={comment['id']}",
        description=_strip_html(html),
        source="direct",
        external_id=f"hn-{comment['id']}",
    )


def fetch_hn_hiring() -> list[Job]:
    hits = _get(HN_SEARCH_URL).json().get("hits", [])
    story = next(
        (h for h in hits if "who is hiring" in (h.get("title") or "").lower()),
        None,
    )
    if story is None:
        return []
    item = _get(HN_ITEM_URL.format(id=story["objectID"])).json()
    return [
        job
        for job in (parse_hn_comment(c) for c in item.get("children", []))
        if job is not None
    ]
