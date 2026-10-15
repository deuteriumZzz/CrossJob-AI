"""Импорт вашего файла с компаниями и HR в базу контактов: Excel, CSV,
TXT, PDF или DOCX (например, ответ Claude Research). Таблицы читаются по
заголовкам столбцов, свободный текст раскладывает по компаниям LLM — но
email принимается, только если он дословно есть в файле: модель не может
«дописать» адрес."""

from __future__ import annotations

import re
import zipfile
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Optional, cast

from src.direct.contacts import extract_emails
from src.direct.import_file_formats import ParsedTable, read_import_file

FIELDS = (
    "company",
    "email",
    "name",
    "position",
    "website",
    "title",
    "source_url",
    "link",
    "telegram",
    "emphasis",
)

# Заголовки столбцов по-русски и по-английски → поле.
_HEADER_SYNONYMS = {
    "company": (
        "компания",
        "company",
        "company name",
        "organization",
        "organization name",
        "организация",
        "работодатель",
        "employer name",
        "employer",
        "название",
    ),
    "email": (
        "email address",
        "e-mail address",
        "contact email",
        "hr email",
        "mail address",
        "электронная почта",
        "почтовый адрес",
        "адрес email",
        "email",
        "e-mail",
        "почта",
        "mail",
        "электронная",
    ),
    "name": (
        "contact name",
        "contact person",
        "recruiter name",
        "hiring manager",
        "hr name",
        "имя",
        "name",
        "контакт",
        "contact",
        "hr",
        "рекрутер",
        "recruiter",
        "фио",
    ),
    # «Должность» рядом с именем — должность человека; вакансия — «Вакансия».
    "position": (
        "contact position",
        "contact role",
        "должность HR",
        "должность контакта",
        "должность",
        "position",
        "роль",
        "role",
    ),
    "website": (
        "company website",
        "company site",
        "careers website",
        "сайт",
        "website",
        "site",
        "домен",
        "domain",
    ),
    "title": (
        "vacancy title",
        "job title",
        "role title",
        "role name",
        "название вакансии",
        "вакансия",
        "vacancy",
        "job",
        "позиция",
        "title",
    ),
    # Где адрес опубликован (например, «Source URL» в careerLauncher) — это
    # не вакансия, а источник контакта. Стоит до «link»: «source url» ⊃ «url».
    "source_url": (
        "email source page",
        "email source",
        "source url",
        "источник контакта",
        "источник",
        "source",
    ),
    "link": (
        "application link",
        "vacancy url",
        "job url",
        "job link",
        "ссылка на вакансию",
        "ссылка",
        "link",
        "url",
        "линк",
    ),
    "telegram": (
        "telegram handle",
        "telegram contact",
        "tg username",
        "telegram",
        "телеграм",
        "tg",
    ),
    "emphasis": (
        "упор",
        "акцент",
        "emphasis",
        "заметк",
        "notes",
        "комментар",
        "описание",
        "description",
    ),
}
# accessibility@, candidate.accommodations@, fraud@, eeo@ — не для откликов.
_NOT_FOR_APPLICATIONS = re.compile(
    r"accessib|accommodat|fraud|eeo|disability", re.I
)
_EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$")


def _normalize_header(header: str) -> str:
    value = re.sub(r"[_-]+", " ", header.strip().casefold())
    return " ".join(re.sub(r"[^\w\s]", " ", value).split())


def _field_for(header: str) -> str | None:
    h = _normalize_header(header)
    if not h or _EMAIL_RE.fullmatch(h):
        return None
    fields = list(_HEADER_SYNONYMS.items())
    for field, words in fields:
        aliases = tuple(_normalize_header(word) for word in words)
        if h in aliases:
            return field
    matches = [
        (len(alias), -field_index, field)
        for field_index, (field, words) in enumerate(fields)
        for alias in (_normalize_header(word) for word in words)
        if _header_contains(h, alias)
    ]
    return max(matches)[2] if matches else None


def _header_contains(header: str, alias: str) -> bool:
    if alias.isascii() and re.fullmatch(r"[a-z0-9 -]+", alias):
        pattern = re.escape(alias).replace(r"\ ", r"\s+")
        return (
            re.search(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", header)
            is not None
        )
    return alias in header


def _table_header(rows: list[list[str]]) -> tuple[int, dict[int, str]]:
    """Find the header row even when a workbook starts with title/notes."""
    candidates: list[tuple[int, int, dict[int, str]]] = []
    for row_index, row in enumerate(rows[:25]):
        mapping = {
            column: field
            for column, value in enumerate(row)
            if (field := _field_for(value))
        }
        fields = set(mapping.values())
        if not fields:
            continue
        # A real table header usually names several fields. Company+email is
        # the strongest signal and prevents a title mentioning "email" from
        # being mistaken for the header.
        score = len(fields) + (4 if {"company", "email"} <= fields else 0)
        candidates.append((score, row_index, mapping))
    if not candidates:
        # Keep custom headings available for the manual mapping step. The
        # widest early row is a safer header candidate than guessing from
        # arbitrary cell contents later in the workbook.
        fallback = max(
            enumerate(rows[:25]),
            key=lambda item: (
                sum(bool(value.strip()) for value in item[1]),
                -item[0],
            ),
            default=None,
        )
        if (
            fallback is None
            or sum(bool(value.strip()) for value in fallback[1]) < 2
        ):
            raise ValueError("Не нашёл строку заголовков таблицы.")
        return fallback[0], {}
    _, row_index, mapping = max(
        candidates, key=lambda item: (item[0], -item[1])
    )
    return row_index, mapping


def table_mapping(
    rows: list[list[str]],
) -> tuple[int, list[str], dict[str, int]]:
    """Return the selected header row and suggested canonical field mapping."""
    header_index, mapping = _table_header(rows)
    if "email" not in mapping.values():
        matches: dict[int, int] = {}
        for row in rows[header_index + 1 : header_index + 26]:
            for column, value in enumerate(row):
                if extract_emails(value):
                    matches[column] = matches.get(column, 0) + 1
        if matches:
            best = max(matches.values())
            columns = [
                column for column, count in matches.items() if count == best
            ]
            if len(columns) == 1:
                mapping[columns[0]] = "email"
    if "company" not in mapping.values() and "email" in mapping.values():
        company_column = _infer_company_column(rows, header_index, mapping)
        if company_column is not None:
            mapping[company_column] = "company"
    # «Title»/«позиция» рядом с именем и email может значить должность
    # человека. Явные «Вакансия» и «Job» остаются названием вакансии.
    if "link" not in mapping.values() and "position" not in mapping.values():
        ambiguous_titles = {
            i
            for i, value in enumerate(rows[header_index])
            if value.strip().casefold() in ("title", "позиция")
            and mapping.get(i) == "title"
        }
        mapping = {
            i: "position" if i in ambiguous_titles else field
            for i, field in mapping.items()
        }
    suggested: dict[str, int] = {}
    for column, field in sorted(mapping.items()):
        suggested.setdefault(field, column)
    return header_index, rows[header_index], suggested


def _infer_company_column(
    rows: list[list[str]], header_index: int, mapping: dict[int, str]
) -> int | None:
    """Infer a company column only when email-row alignment is strong."""
    email_column = next(
        column for column, field in mapping.items() if field == "email"
    )
    body = rows[header_index + 1 : header_index + 41]
    email_rows = [
        row
        for row in body
        if email_column < len(row) and extract_emails(row[email_column])
    ]
    if len(email_rows) < 2:
        return None
    excluded_headers = (
        "location",
        "country",
        "city",
        "format",
        "status",
        "salary",
        "date",
        "description",
        "notes",
        "source",
        "website",
        "domain",
        "url",
        "link",
        "телефон",
        "город",
        "страна",
        "формат",
        "статус",
        "зарплат",
        "дата",
        "описан",
        "замет",
        "источник",
        "сайт",
        "домен",
        "ссыл",
    )
    used_columns = set(mapping)
    header = rows[header_index]
    scored: list[tuple[float, int]] = []
    width = max((len(row) for row in email_rows), default=0)
    for column in range(width):
        if column in used_columns:
            continue
        label = (
            _normalize_header(header[column]) if column < len(header) else ""
        )
        if any(term in label for term in excluded_headers):
            continue
        values = [
            row[column].strip() for row in email_rows if column < len(row)
        ]
        valid = [
            value
            for value in values
            if value
            and len(value) <= 120
            and len(value.split()) <= 12
            and re.search(r"[A-Za-zА-Яа-яЁё]", value)
            and not extract_emails(value)
            and not re.search(r"https?://|www\.", value, re.I)
        ]
        coverage = len(valid) / len(email_rows)
        if coverage < 0.7:
            continue
        unique_ratio = len({value.casefold() for value in valid}) / len(valid)
        concise_ratio = sum(len(value.split()) <= 5 for value in valid) / len(
            valid
        )
        score = coverage * 0.55 + unique_ratio * 0.25 + concise_ratio * 0.2
        scored.append((score, column))
    scored.sort(reverse=True)
    if not scored or scored[0][0] < 0.72:
        return None
    if len(scored) > 1 and scored[0][0] - scored[1][0] < 0.08:
        return None
    return scored[0][1]


def rows_from_table(
    rows: list[list[str]], field_mapping: dict[str, int | None] | None = None
) -> list[dict]:
    header_index, _, suggested = table_mapping(rows)
    body = rows[header_index + 1 :]
    if field_mapping is None:
        selected = suggested
    else:
        selected = {
            field: column
            for field, column in field_mapping.items()
            if field in FIELDS
            and column is not None
            and 0 <= column < len(rows[header_index])
        }
    mapping = {column: field for field, column in selected.items()}
    if "email" not in mapping.values() and "company" not in mapping.values():
        raise ValueError(
            "Не нашёл столбцы «Компания» и «Email» — проверьте заголовки "
            "таблицы."
        )
    result = []
    normalized_header = [
        _normalize_header(value) for value in rows[header_index]
    ]
    for number, row in enumerate(body, start=header_index + 2):
        normalized_row = [_normalize_header(value) for value in row]
        if normalized_row == normalized_header:
            continue
        item: dict[str, Any] = {f: "" for f in FIELDS}
        for i, value in enumerate(row):
            field = mapping.get(i)
            if field and value.strip() and not item[field]:
                item[field] = value.strip()
        # В ячейке бывает «hr@x.ru, careers@x.ru» — берём первый адрес.
        emails = extract_emails(item["email"]) if item["email"] else []
        item["email"] = emails[0] if emails else item["email"].lower()
        item["telegram"] = (
            item["telegram"].replace("https://t.me/", "").lstrip("@")
        )
        item["row"] = number
        if item["company"] or item["email"]:
            result.append(item)
    return result


def read_file(
    filename: str,
    data: bytes,
    *,
    on_ocr_progress: Callable[[int, int], None] | None = None,
) -> tuple[list[list[str]] | None, str]:
    """Read a supported file, using the importer's field mapping rules."""
    return read_import_file(
        filename,
        data,
        fields=FIELDS,
        field_for=_field_for,
        table_mapping=table_mapping,
        rows_from_table=rows_from_table,
        on_ocr_progress=on_ocr_progress,
    )


CHUNK_CHARS = (
    6000  # столько текста за один запрос к LLM — большой PDF идёт частями
)


def _chunks(text: str) -> list[str]:
    """Режем по строкам, чтобы компания не разрывалась посередине."""
    chunks, current = [], ""
    lines = [
        piece
        for line in text.splitlines(keepends=True)
        for piece in (
            line[i : i + CHUNK_CHARS] for i in range(0, len(line), CHUNK_CHARS)
        )
    ]
    for line in lines:
        if current and len(current) + len(line) > CHUNK_CHARS:
            chunks.append(current)
            current = ""
        current += line
    if current.strip():
        chunks.append(current)
    return chunks


def rows_from_text(
    text: str,
    llm_api_key: str,
    progress: Optional[Callable[[int, int], None]] = None,
) -> list[dict]:
    """Свободный текст → компании через LLM, по частям. Адреса, которых
    нет в исходном тексте дословно, отбрасываются (защита от выдумок), а
    адреса из текста, которые модель пропустила, добавляются строкой с
    компанией по домену — чтобы из большого файла ничего не потерялось."""
    from langchain_core.language_models import BaseChatModel
    from langchain_core.prompts import ChatPromptTemplate
    from pydantic import BaseModel, Field

    from src.job_sources.llm_provider import get_chat_llm

    class _Company(BaseModel):
        company: str = ""
        email: str = ""
        name: str = Field(
            default="", description="Имя контакта/рекрутера, если есть"
        )
        website: str = ""
        title: str = Field(default="", description="Вакансия, если упомянута")
        emphasis: str = Field(
            default="", description="На что сделать упор в письме"
        )

    class _Companies(BaseModel):
        companies: list[_Company]

    prompt = ChatPromptTemplate.from_template(
        "Разложи список компаний из текста по полям. Бери только то, что "
        "написано в тексте, ничего не придумывай; поля без данных — "
        "пустые.\n\n{text}"
    )
    llm = cast(BaseChatModel, get_chat_llm(llm_api_key, temperature=0))
    parts = _chunks(text)
    parsed: list = []
    failed = 0
    for index, part in enumerate(parts):
        if progress:
            progress(index, len(parts))
        try:
            parsed += cast(
                _Companies,
                llm.with_structured_output(_Companies).invoke(
                    prompt.format(text=part)
                ),
            ).companies
        except Exception as e:
            failed += 1
            from src.logging import logger

            logger.warning(
                f"Импорт: часть {index + 1}/{len(parts)} не разобрана LLM: {e}"
            )
    if parts and failed == len(parts) and not extract_emails(text):
        raise ValueError(
            "ИИ не смог разобрать файл — проверьте ключ ИИ или сохраните "
            "список как CSV/XLSX."
        )
    if progress:
        progress(len(parts), len(parts))
    source_emails = {e.lower() for e in extract_emails(text)}
    result = []
    for number, c in enumerate(parsed, start=1):
        email = c.email.strip().lower()
        item: dict[str, Any] = {f: "" for f in FIELDS}
        item.update(
            company=c.company.strip(),
            name=c.name.strip(),
            website=c.website.strip(),
            title=c.title.strip(),
            emphasis=c.emphasis.strip(),
            email=email if email in source_emails else "",
            row=number,
        )
        if item["company"] or item["email"]:
            result.append(item)
    found = {r["email"] for r in result}
    for email in sorted(source_emails - found):
        item = {f: "" for f in FIELDS}
        domain = email.split("@")[1]
        labels = domain.split(".")
        # acme.co.uk → Acme, mail.acme.io → Acme
        name = (
            labels[-3]
            if len(labels) > 2
            and labels[-2] in ("co", "com", "org", "net", "ac")
            else labels[-2]
        )
        item.update(
            email=email,
            website=domain,
            row=len(result) + 1,
            company=name.capitalize(),
        )
        result.append(item)
    return result


# --- проверка адресов ----------------------------------------------------

_MX_CACHE: dict[str, bool | None] = {}


def domain_accepts_mail(domain: str) -> bool | None:
    """Есть ли у домена почтовый сервер (MX). None — проверить нечем."""
    if domain in _MX_CACHE:
        return _MX_CACHE[domain]
    try:
        import dns.resolver

        try:
            dns.resolver.resolve(domain, "MX", lifetime=5)
            ok: bool | None = True
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
            ok = False
        except Exception:
            ok = None
    except ImportError:
        ok = None
    _MX_CACHE[domain] = ok
    return ok


def check_email(email: str) -> tuple[str, str]:
    """(статус, пояснение): ok / bad / unknown."""
    if not _EMAIL_RE.match(email):
        return "bad", "неверный формат адреса"
    if _NOT_FOR_APPLICATIONS.search(email.split("@")[0]):
        return "bad", "ящик для доступности/жалоб, а не для откликов"
    accepts = domain_accepts_mail(email.split("@")[1])
    if accepts is False:
        return "bad", "у домена нет почтового сервера — письмо не дойдёт"
    if accepts is None:
        return "unknown", "домен не проверен"
    return "ok", ""


def preview(
    rows: list[dict], known_emails: set[str], written_emails: set[str]
) -> dict:
    """Что будет импортировано: сводка и строки с пометками."""
    # Домены проверяем параллельно — иначе сотня адресов ждёт минуты.
    domains = {
        r["email"].split("@")[1].lower() for r in rows if "@" in r["email"]
    }
    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(domain_accepts_mail, domains - set(_MX_CACHE)))
    seen: set[str] = set()
    items = []
    stats = {
        "total": len(rows),
        "ok": 0,
        "bad": 0,
        "unknown": 0,
        "duplicate": 0,
        "already_written": 0,
    }
    for row in rows:
        email = row["email"].lower()
        if not email:
            check, note = "bad", "нет email"
        elif email in seen:
            check, note = "duplicate", "повтор в файле"
        else:
            check, note = check_email(email)
            if email in written_emails:
                check, note = "written", "уже писали — повторно не отправим"
                stats["already_written"] += 1
            elif email in known_emails and not note:
                note = "уже есть в базе — дополним"
        if check in stats:
            stats[check] += 1
        seen.add(email)
        items.append({**row, "check": check, "note": note})
    return {"stats": stats, "items": items}
