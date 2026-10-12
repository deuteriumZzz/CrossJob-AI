"""Expose accepted Hirify vacancies in the shared message workspace."""

import re
from pathlib import Path

from src.job import Job
from src.job_sources.contact_book import ContactBook
from src.job_sources.hirify.mapping import hirify_apply_contacts
from src.job_sources.telegram.watcher import (
    get_watch_post,
    list_watch_posts,
    save_watch_post,
)

_HIRIFY_JOB_URL = re.compile(r"https://hirify\.me/jobs/(\d+)-([A-Za-z0-9-]+)")


class HirifyLoginRequired(ValueError):
    """The app's Hirify browser profile is not signed in."""


def save_hirify_vacancy(
    output_folder: Path, job: Job, contacts: list[dict], found_at: str = ""
) -> str:
    """Save a candidate conversation without sending or scheduling it.

    The Hirify page URL gives this item a stable ID distinct from a
    Telegram channel post. A repeated scan keeps the prior status, draft,
    and removal tombstone because no status is supplied here.
    """
    selected: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for item in contacts:
        kind = str(item.get("kind", ""))
        value = str(item.get("value", "")).strip().lstrip("@")
        key = (kind, value.lower())
        if kind not in ("telegram", "email") or not value or key in seen:
            continue
        seen.add(key)
        selected.append(
            {
                "kind": kind,
                "value": value,
                **{
                    name: item[name]
                    for name in ("source", "source_url")
                    if isinstance(item.get(name), str) and item[name]
                },
            }
        )
    post = {
        "source": "hirify",
        "channel": "Hirify",
        "company": job.company,
        "title": job.role,
        "text": job.description[:4000],
        "link": job.link,
        "contacts": selected,
    }
    if found_at:
        post["found_at"] = found_at
    return save_watch_post(output_folder, post)


def refresh_hirify_post_contacts(
    output_folder: Path, post_id: str, client
) -> dict:
    """Read a saved vacancy's contact dialog and persist verified addresses.

    A click in the user's separate browser cannot update this database, so
    the app calls this from its own explicit refresh action using its login
    profile. Existing draft, status, and manually added contacts are kept.
    """
    post = get_watch_post(output_folder, post_id)
    if not post or post.get("source") != "hirify":
        raise ValueError("Вакансия Hirify не найдена")
    match = _HIRIFY_JOB_URL.fullmatch(str(post.get("link") or ""))
    if match is None:
        raise ValueError("Неверная ссылка вакансии Hirify")
    if post.get("status") in ("removed", "source_deleted"):
        raise ValueError("Эта вакансия удалена")
    info = client.show_contacts(*match.groups())
    if info.get("needs_login"):
        raise HirifyLoginRequired(
            "Войдите в Hirify в окне приложения и повторите поиск контактов"
        )
    channels = tuple(info.get("channels") or ())
    discovered = [
        {
            **item,
            "source": "Hirify: контакты",
            "source_url": post["link"],
        }
        for item in hirify_apply_contacts(info.get("text") or "", channels)
        if item.get("kind") in ("telegram", "email")
    ]
    if not discovered:
        raise ValueError(
            "Hirify не показал Telegram или email. "
            "Проверьте вход и контакты на сайте"
        )
    existing = post.get("contacts") or []
    keys = {
        (item.get("kind"), str(item.get("value", "")).lower())
        for item in existing
    }
    merged = [*existing]
    for item in discovered:
        key = (item["kind"], item["value"].lower())
        if key not in keys:
            merged.append(item)
            keys.add(key)
    job = Job(
        role=str(post.get("title") or ""),
        company=str(post.get("company") or ""),
        description=str(post.get("text") or ""),
        link=post["link"],
        source="hirify",
    )
    ContactBook(output_folder).add(
        job.company,
        discovered,
        vacancy={
            "title": job.role,
            "link": job.link,
            "source": "hirify",
            "text": job.description[:4000],
        },
    )
    save_hirify_vacancy(output_folder, job, merged)
    saved = get_watch_post(output_folder, post_id) or {}
    return {
        "contacts": saved.get("contacts", []),
        "channels": list(channels),
    }


def backfill_hirify_vacancies(output_folder: Path) -> int:
    """Show previously saved Hirify jobs without rediscovering or sending.

    Contacts match by their exact source URL: a company may have several
    vacancies, and an unrelated contact is not a safe presumed recipient.
    """
    existing = {
        post.get("link") for post in list_watch_posts(output_folder).values()
    }
    created = 0
    for card in ContactBook(output_folder).all().values():
        for vacancy in card.get("vacancies") or []:
            link = str(vacancy.get("link") or "")
            if (
                vacancy.get("source") != "hirify"
                or not link.startswith("https://hirify.me/jobs/")
                or link in existing
            ):
                continue
            contacts = [
                contact
                for contact in card.get("contacts") or []
                if contact.get("source_url") == link
            ]
            job = Job(
                role=str(vacancy.get("title") or ""),
                company=str(card.get("company") or ""),
                description=str(vacancy.get("text") or ""),
                link=link,
                source="hirify",
            )
            save_hirify_vacancy(
                output_folder,
                job,
                contacts,
                found_at=str(vacancy.get("found_at") or ""),
            )
            existing.add(link)
            created += 1
    return created
