"""Импорт вашего файла с компаниями и HR в базу контактов: Excel, CSV,
TXT, PDF или DOCX (например, ответ Claude Research). Таблицы читаются по
заголовкам столбцов, свободный текст раскладывает по компаниям LLM — но
email принимается, только если он дословно есть в файле: модель не может
«дописать» адрес."""

from __future__ import annotations

import csv
import io
import re
import zipfile
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Optional, cast
from xml.etree import ElementTree as ET

from src.direct.contacts import extract_emails

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


def _field_for(header: str) -> str | None:
    h = header.strip().casefold()
    if not h or _EMAIL_RE.fullmatch(h):
        return None
    fields = list(_HEADER_SYNONYMS.items())
    for field, words in fields:
        if h in words:
            return field
    matches = [
        (len(word), -field_index, field)
        for field_index, (field, words) in enumerate(fields)
        for word in words
        if _header_contains(h, word)
    ]
    return max(matches)[2] if matches else None


def _header_contains(header: str, alias: str) -> bool:
    if alias.isascii() and re.fullmatch(r"[a-z0-9 -]+", alias):
        pattern = re.escape(alias).replace(r"\ ", r"\s+")
        return re.search(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", header) is not None
    return alias in header


# --- чтение форматов -----------------------------------------------------


def _xlsx_rows(data: bytes) -> list[list[str]]:
    m = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(
                f"{m}si"
            ):
                shared.append("".join(t.text or "" for t in si.iter(f"{m}t")))
        sheet = sorted(
            n for n in z.namelist() if n.startswith("xl/worksheets/sheet")
        )[0]
        rows = []
        for row in ET.fromstring(z.read(sheet)).iter(f"{m}row"):
            values: dict[int, str] = {}
            for cell in row.iter(f"{m}c"):
                ref = re.match(r"[A-Z]+", cell.get("r", "A"))
                letters = ref.group(0) if ref else "A"
                col = 0
                for ch in letters:
                    col = col * 26 + ord(ch) - 64
                v = cell.find(f"{m}v")
                inline = cell.find(f".//{m}t")
                if cell.get("t") == "s" and v is not None:
                    value = shared[int(v.text or 0)]
                elif inline is not None:
                    value = inline.text or ""
                else:
                    value = v.text if v is not None and v.text else ""
                values[col - 1] = value
            if values:
                rows.append(
                    [values.get(i, "") for i in range(max(values) + 1)]
                )
        return rows


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1251"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(
        "Не удалось прочитать кодировку файла — сохраните его в UTF-8."
    )


def _csv_rows(data: bytes) -> list[list[str]]:
    text = _decode(data)
    try:
        dialect = csv.Sniffer().sniff(text[:4000], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return [
        row
        for row in csv.reader(io.StringIO(text), dialect)
        if any(c.strip() for c in row)
    ]


def _docx_text(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    return "\n".join(
        "".join(t.text or "" for t in p.iter(f"{w}t"))
        for p in root.iter(f"{w}p")
    )


def _markdown_rows(text: str) -> list[list[str]] | None:
    """Таблица Markdown (| a | b |) — строки без разделителя |---|."""
    rows = [
        [
            cell.strip().strip("`")
            for cell in line.strip().strip("|").split("|")
        ]
        for line in text.splitlines()
        if line.strip().startswith("|") and not re.fullmatch(r"[\s|:-]+", line)
    ]
    return rows if len(rows) > 1 else None


def _pdf_table_rows(data: bytes) -> list[list[str]] | None:
    """Таблица из PDF по координатам: строки — по высоте, столбец — по
    ближайшему заголовку. Без ИИ, так что email не «съедет» в чужую
    строку. None — в PDF нет таблицы с заголовками «Компания»/«Email»."""
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTTextContainer, LTTextLine

    header: list[str] = []
    centers: list[float] = []
    rows: list[list[str]] = []
    page_rows: list[tuple[float, list[str]]] = []
    for page in extract_pages(io.BytesIO(data)):
        lines = sorted(
            (
                (line.y0, (line.x0 + line.x1) / 2, line.get_text().strip())
                for box in page
                if isinstance(box, LTTextContainer)
                for line in box
                if isinstance(line, LTTextLine) and line.get_text().strip()
            ),
            key=lambda t: -t[0],
        )
        groups: list[list[tuple[float, float, str]]] = []
        for (
            line
        ) in lines:  # одна строка таблицы — ячейки с почти одной высотой
            if groups and groups[-1][0][0] - line[0] < 2:
                groups[-1].append(line)
            else:
                groups.append([line])
        for group in groups:
            cells = sorted((x, text) for _, x, text in group)
            texts = [t for _, t in cells]
            if not header:
                fields = {_field_for(t) for t in texts}
                if "email" in fields and ({"company", "name"} & fields):
                    header, centers = texts, [x for x, _ in cells]
                continue
            if texts == header:
                continue  # заголовок повторяется на каждой странице
            row = [""] * len(header)
            for x, text in cells:
                i = min(range(len(centers)), key=lambda i: abs(centers[i] - x))
                row[i] = _join_cell(row[i], text)
            page_rows.append((group[0][0], row))
        rows += _merge_wrapped(page_rows, len(header))
        page_rows = []
    return [header, *rows] if header and rows else None


def _join_cell(head: str, tail: str) -> str:
    """Перенос внутри ячейки: «name@site.» + «com» — без пробела."""
    if not head:
        return tail
    return head + tail if head[-1] in ".@-_" else f"{head} {tail}"


def _merge_wrapped(
    rows: list[tuple[float, list[str]]], width: int
) -> list[list[str]]:
    """Длинная ячейка переносится на строку выше/ниже остальных — такой
    обрывок (заполнено меньше половины ячеек) приклеиваем к ближайшей
    по высоте полной строке, сверху вниз."""
    full = [
        i
        for i, (_, row) in enumerate(rows)
        if sum(1 for c in row if c) * 2 >= width
    ]
    if not full:
        return [row for _, row in rows]
    parts: dict[int, list[int]] = {i: [] for i in full}
    for i, (y, _) in enumerate(rows):
        owner = (
            i if i in parts else min(full, key=lambda f: abs(rows[f][0] - y))
        )
        parts[owner].append(i)
    merged = []
    for owner in full:
        row = [""] * width
        for i in sorted(
            parts[owner], key=lambda i: -rows[i][0]
        ):  # сверху вниз
            for c, text in enumerate(rows[i][1]):
                if text:
                    row[c] = _join_cell(row[c], text)
        merged.append(row)
    return merged


def read_file(
    filename: str, data: bytes
) -> tuple[list[list[str]] | None, str]:
    """(строки таблицы, "") для CSV/XLSX/таблицы Markdown или (None, текст)."""
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext == "md":
        text = _decode(data)
        return _markdown_rows(text), text
    if ext == "xlsx":
        return _xlsx_rows(data), ""
    if ext in ("csv", "tsv"):
        return _csv_rows(data), ""
    if ext == "docx":
        return None, _docx_text(data)
    if ext == "pdf":
        from pdfminer.high_level import extract_text

        table = _pdf_table_rows(data)
        return (table, "") if table else (None, extract_text(io.BytesIO(data)))
    return None, _decode(data)


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
            key=lambda item: (sum(bool(value.strip()) for value in item[1]), -item[0]),
            default=None,
        )
        if fallback is None or sum(bool(value.strip()) for value in fallback[1]) < 2:
            raise ValueError("Не нашёл строку заголовков таблицы.")
        return fallback[0], {}
    _, row_index, mapping = max(candidates, key=lambda item: (item[0], -item[1]))
    return row_index, mapping


def table_mapping(rows: list[list[str]]) -> tuple[int, list[str], dict[str, int]]:
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
            columns = [column for column, count in matches.items() if count == best]
            if len(columns) == 1:
                mapping[columns[0]] = "email"
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
    for number, row in enumerate(body, start=header_index + 2):
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
