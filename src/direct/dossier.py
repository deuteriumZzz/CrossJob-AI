"""Досье компании по запросу (кнопка «Досье» во вкладке «Контакты»):
сайт компании → страницы «Контакты/Карьера/Команда» → реальные email,
Telegram и LinkedIn со страниц; плюс проверенные HR-адреса Hunter,
если задан ключ. Только то, что опубликовано, — с указанием страницы.

Сайт берётся из уже найденного: карточка, домен рабочего email, ссылка
в тексте вакансии (открытый API hh без входа отвечает 403 — проверено
2026-09-24)."""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import httpx

from src.direct.contacts import hunter_hr_contacts
from src.job_sources.contact_book import contacts_from_text

TIMEOUT = 15
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; CrossJob-AI)"}
MAX_PAGES = 6

# Бесплатные почтовые сервисы — их домен не сайт компании.
_FREE_MAIL = {
    "gmail.com", "yandex.ru", "ya.ru", "mail.ru", "bk.ru", "list.ru",
    "inbox.ru", "outlook.com", "hotmail.com", "yahoo.com", "icloud.com",
    "proton.me", "protonmail.com", "rambler.ru",
}
# Ссылки, которые сайтом компании не являются.
_NOT_COMPANY = (
    "t.me", "telegram", "hh.ru", "linkedin.com", "habr.com", "getmatch",
    "google.", "forms.", "notion.", "instagram", "facebook", "vk.com",
    "youtube", "twitter", "x.com", "github.com",
)
_URL_RE = re.compile(r"https?://[^\s)\"'<>]+")
_HREF_RE = re.compile(r'href=["\']([^"\'#]+)["\']', re.IGNORECASE)
_INTERESTING_LINK_RE = re.compile(
    r"contact|career|jobs?|vacanc|hiring|team|about|join|kontakt|"
    r"контакт|вакан|карьер|команд|о-компании",
    re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^>]+>")
_CODE_BLOCK_RE = re.compile(r"<(script|style)\b.*?</\1>", re.IGNORECASE | re.DOTALL)


def candidate_websites(card: dict) -> list[str]:
    sites = [card["website"]] if card.get("website") else []
    for contact in card.get("contacts", []):
        if contact["kind"] == "email":
            domain = contact["value"].split("@")[-1].lower()
            if domain not in _FREE_MAIL:
                sites.append(domain)
    for vacancy in card.get("vacancies", []):
        for url in _URL_RE.findall(vacancy.get("text", "")):
            host = urlparse(url).netloc.lower()
            if host and not any(bad in host for bad in _NOT_COMPANY):
                sites.append(host)
    seen: list[str] = []
    for site in sites:
        site = site.removeprefix("www.")
        if site and site not in seen:
            seen.append(site)
    return seen


def _get(url: str) -> httpx.Response | None:
    try:
        response = httpx.get(
            url, timeout=TIMEOUT, headers=_HEADERS, follow_redirects=True
        )
    except httpx.HTTPError:
        return None
    return response if response.status_code == 200 else None


def collect_dossier(card: dict, hunter_key: str = "") -> dict:
    """{"website", "contacts": [...]} — контакты со страниц сайта
    компании и из Hunter, у каждого — где найден."""
    contacts: list[dict] = []
    website = ""
    for site in candidate_websites(card):
        home = _get(site if site.startswith("http") else f"https://{site}")
        if home is None:
            continue
        website = str(home.url)
        host = home.url.host.removeprefix("www.")
        pages = [home]
        links = [
            urljoin(website, href)
            for href in _HREF_RE.findall(home.text)
            if _INTERESTING_LINK_RE.search(href)
        ]
        for link in dict.fromkeys(links):
            if len(pages) >= MAX_PAGES:
                break
            if urlparse(link).netloc.removeprefix("www.") != host:
                continue
            page = _get(link)
            if page is not None:
                pages.append(page)
        for page in pages:
            html = _CODE_BLOCK_RE.sub(" ", page.text)
            text = _TAG_RE.sub(" ", html)
            hrefs = " ".join(_HREF_RE.findall(html))
            for contact in contacts_from_text(f"{text} {hrefs}", bare_mentions=False):
                contacts.append(
                    {
                        **contact,
                        "source": f"сайт: {page.url.path or '/'}",
                        "source_url": str(page.url),
                    }
                )
        break

    domain = urlparse(website).netloc.removeprefix("www.") if website else ""
    if hunter_key and domain:
        try:
            for person in hunter_hr_contacts(domain, hunter_key):
                contacts.append(
                    {
                        "kind": "email",
                        "value": person["email"],
                        "name": person["name"],
                        "position": person["position"],
                        "source": f"Hunter, проверен {person['confidence']}%",
                        "source_url": f"https://hunter.io/search/{domain}",
                    }
                )
        except httpx.HTTPError:
            pass
    return {"website": website, "contacts": contacts}
