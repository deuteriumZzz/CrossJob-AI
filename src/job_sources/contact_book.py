"""Книга контактов — вкладка «Контакты» в дашборде: компании и люди,
которым можно написать напрямую. Сюда пишут все сборщики (текст
вакансий, Telegram-каналы, досье компании), у каждого контакта —
источник и дата. Только то, что реально найдено в источнике: без
угаданных адресов.

ponytail: собирается под вакансии, на которые вы смотрите, а не база
"впрок" — массовый сбор контактов людей это обработка персональных
данных (152-ФЗ) и прямой путь к спаму."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from src.direct.contacts import extract_emails
from src.utils.file_lock import state_file_lock

CONTACT_BOOK_FILE = "contact_book.json"

_LEGAL_FORMS_RE = re.compile(
    r"\b(ооо|оао|зао|пао|ао|ип|llc|inc|ltd|gmbh|corp|co|plc|bv|ag|sa)\b"
)
_NON_WORD_RE = re.compile(r"[\W_]+")
# @username — но не "@acme" внутри адреса anna@acme.io.
_TELEGRAM_RE = re.compile(
    r"(?:t\.me/|(?<![\w.])@)([a-zA-Z][a-zA-Z0-9_]{4,31})\b"
)
_TELEGRAM_LINK_RE = re.compile(r"t\.me/([a-zA-Z][a-zA-Z0-9_]{4,31})\b")
_LINKEDIN_RE = re.compile(
    r"https?://(?:[\w-]+\.)?linkedin\.com/in/[\w%-]+/?"
)


# Общие почтовые сервисы — по ним компанию не узнать.
_FREE_MAIL = {
    "gmail.com", "googlemail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com",
    "proton.me", "protonmail.com", "mail.ru", "bk.ru", "list.ru", "inbox.ru", "yandex.ru",
    "ya.ru", "yandex.com", "rambler.ru", "gmx.com", "aol.com", "live.com",
}


def _domain(value: str) -> str:
    """acme.io из «https://www.acme.io/jobs» или «hr@acme.io»; пусто для gmail и т.п."""
    value = value.strip().lower()
    host = value.split("@", 1)[1] if "@" in value else re.sub(r"^[a-z]+://", "", value).split("/")[0]
    host = host.removeprefix("www.")
    return "" if not host or "." not in host or host in _FREE_MAIL else host


def _card_domains(card: dict) -> set[str]:
    values = [card.get("website") or ""] + [c["value"] for c in card["contacts"] if c["kind"] == "email"]
    return {d for d in map(_domain, values) if d}


def company_key(company: str) -> str:
    text = _LEGAL_FORMS_RE.sub(" ", company.casefold())
    return _NON_WORD_RE.sub(" ", text).strip()


def contacts_from_text(
    text: str, exclude: tuple[str, ...] = (), bare_mentions: bool = True
) -> list[dict]:
    """Все контакты из свободного текста (пост, описание вакансии):
    email, @username/t.me-ссылки, профили LinkedIn. exclude — ники,
    которые контактом не считаются (сам канал, боты-репостеры).
    bare_mentions=False — только ссылки t.me (для веб-страниц, где "@"
    чаще CSS-правило или соцсеть, чем Telegram)."""
    skip = {e.lower() for e in exclude}
    found: list[dict] = [
        {"kind": "email", "value": e} for e in extract_emails(text)
    ]
    telegram_re = _TELEGRAM_RE if bare_mentions else _TELEGRAM_LINK_RE
    usernames = {
        u for u in telegram_re.findall(text) if u.lower() not in skip
    }
    found += [{"kind": "telegram", "value": u} for u in sorted(usernames)]
    found += [
        {"kind": "linkedin", "value": u.rstrip("/")}
        for u in sorted(set(_LINKEDIN_RE.findall(text)))
    ]
    return found


class ContactBook:
    def __init__(self, output_folder: Path):
        self.path = output_folder / CONTACT_BOOK_FILE

    def _load(self) -> dict:
        if not self.path.exists():
            return {"companies": {}}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"companies": {}}

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def add(
        self,
        company: str,
        contacts: list[dict],
        vacancy: dict | None = None,
        website: str = "",
        emphasis: str = "",
    ) -> str:
        """contacts: [{kind, value, source, source_url, name?, position?}].
        Компания без названия (пост в Telegram без компании) заводится
        по первому контакту — иначе все такие посты слиплись бы в одну.
        Повторный контакт не дублируется. Возвращает ключ компании."""
        key = company_key(company) or (
            f"@{contacts[0]['value']}" if contacts else ""
        )
        if not key:
            return ""
        now = datetime.now().astimezone().isoformat()
        with state_file_lock(self.path):
            data = self._load()
            if key not in data["companies"]:
                # «Acme», «ACME LLC» и acme.io — одна компания: ищем по домену
                # сайта/почты, иначе одной компании ушло бы два письма.
                incoming = _card_domains({"website": website, "contacts": contacts})
                key = next(
                    (k for k, c in data["companies"].items() if incoming & _card_domains(c)), key
                )
            card = data["companies"].setdefault(
                key,
                {
                    "company": company,
                    "website": "",
                    "vacancies": [],
                    "contacts": [],
                    "created_at": now,
                },
            )
            if company and not card["company"]:
                card["company"] = company
            if website and not card["website"]:
                card["website"] = website
            if emphasis and not card.get("emphasis"):
                # «На что сделать упор» из вашего файла — для письма.
                card["emphasis"] = emphasis
            if vacancy and vacancy.get("link") and all(
                v["link"] != vacancy["link"] for v in card["vacancies"]
            ):
                card["vacancies"].append({**vacancy, "found_at": now})
            known = {(c["kind"], c["value"].lower()) for c in card["contacts"]}
            for contact in contacts:
                ident = (contact["kind"], contact["value"].lower())
                if contact.get("value") and ident not in known:
                    card["contacts"].append({**contact, "found_at": now})
                    known.add(ident)
            card["updated_at"] = now
            self._save(data)
        return key

    def all(self) -> dict:
        return self._load()["companies"]

    def update(self, keys: list[str], **fields) -> None:
        """Поля нескольких компаний сразу (например, do_not_contact)."""
        with state_file_lock(self.path):
            data = self._load()
            for key in keys:
                if key in data["companies"]:
                    data["companies"][key].update(fields)
            self._save(data)

    def delete(self, keys: list[str]) -> list[dict]:
        """Удаляет компании, возвращает удалённые — для «Отменить»."""
        with state_file_lock(self.path):
            data = self._load()
            removed = [{"key": k, **data["companies"].pop(k)} for k in keys if k in data["companies"]]
            self._save(data)
        return removed

    def restore(self, cards: list[dict]) -> None:
        with state_file_lock(self.path):
            data = self._load()
            for card in cards:
                card = dict(card)
                data["companies"][card.pop("key")] = card
            self._save(data)

    def get(self, key: str) -> dict | None:
        return self.all().get(key)
