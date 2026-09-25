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
from typing import Callable, Optional, cast
from xml.etree import ElementTree as ET

from src.direct.contacts import extract_emails

FIELDS = ("company", "email", "name", "position", "website", "title", "source_url", "link", "telegram", "emphasis")

# Заголовки столбцов по-русски и по-английски → поле.
_HEADER_SYNONYMS = {
    "company": ("компания", "company", "организация", "работодатель", "employer", "название"),
    "email": ("email", "e-mail", "почта", "mail", "электронная"),
    "name": ("имя", "name", "контакт", "contact", "hr", "рекрутер", "recruiter", "фио"),
    "position": ("должность контакта", "position", "роль", "role"),
    "website": ("сайт", "website", "site", "домен", "domain"),
    "title": ("вакансия", "vacancy", "job", "позиция", "title"),
    # Где адрес опубликован (например, «Source URL» в careerLauncher) — это
    # не вакансия, а источник контакта. Стоит до «link»: «source url» ⊃ «url».
    "source_url": ("источник", "source url", "source"),
    "link": ("ссылка", "link", "url", "линк"),
    "telegram": ("telegram", "телеграм", "tg"),
    "emphasis": ("упор", "акцент", "emphasis", "заметк", "notes", "комментар", "описание", "description"),
}
# accessibility@, candidate.accommodations@, fraud@, eeo@ — не для откликов.
_NOT_FOR_APPLICATIONS = re.compile(r"accessib|accommodat|fraud|eeo|disability", re.I)
_EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$")


def _field_for(header: str) -> str | None:
    h = header.strip().casefold()
    if not h:
        return None
    for field, words in _HEADER_SYNONYMS.items():
        if h in words:
            return field
    for field, words in _HEADER_SYNONYMS.items():
        if any(w in h for w in words):
            return field
    return None


# --- чтение форматов -----------------------------------------------------

def _xlsx_rows(data: bytes) -> list[list[str]]:
    m = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(f"{m}si"):
                shared.append("".join(t.text or "" for t in si.iter(f"{m}t")))
        sheet = sorted(n for n in z.namelist() if n.startswith("xl/worksheets/sheet"))[0]
        rows = []
        for row in ET.fromstring(z.read(sheet)).iter(f"{m}row"):
            values: dict[int, str] = {}
            for cell in row.iter(f"{m}c"):
                letters = re.match(r"[A-Z]+", cell.get("r", "A")).group(0)
                col = 0
                for ch in letters:
                    col = col * 26 + ord(ch) - 64
                v = cell.find(f"{m}v")
                inline = cell.find(f".//{m}t")
                if cell.get("t") == "s" and v is not None:
                    value = shared[int(v.text)]
                elif inline is not None:
                    value = inline.text or ""
                else:
                    value = v.text if v is not None and v.text else ""
                values[col - 1] = value
            if values:
                rows.append([values.get(i, "") for i in range(max(values) + 1)])
        return rows


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1251"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Не удалось прочитать кодировку файла — сохраните его в UTF-8.")


def _csv_rows(data: bytes) -> list[list[str]]:
    text = _decode(data)
    try:
        dialect = csv.Sniffer().sniff(text[:4000], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return [row for row in csv.reader(io.StringIO(text), dialect) if any(c.strip() for c in row)]


def _docx_text(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    return "\n".join("".join(t.text or "" for t in p.iter(f"{w}t")) for p in root.iter(f"{w}p"))


def _markdown_rows(text: str) -> list[list[str]] | None:
    """Таблица Markdown (| a | b |) — строки без разделителя |---|."""
    rows = [
        [cell.strip().strip("`") for cell in line.strip().strip("|").split("|")]
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
            ((line.y0, (line.x0 + line.x1) / 2, line.get_text().strip())
             for box in page if isinstance(box, LTTextContainer)
             for line in box if isinstance(line, LTTextLine) and line.get_text().strip()),
            key=lambda t: -t[0],
        )
        groups: list[list[tuple[float, float, str]]] = []
        for line in lines:  # одна строка таблицы — ячейки с почти одной высотой
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


def _merge_wrapped(rows: list[tuple[float, list[str]]], width: int) -> list[list[str]]:
    """Длинная ячейка переносится на строку выше/ниже остальных — такой
    обрывок (заполнено меньше половины ячеек) приклеиваем к ближайшей
    по высоте полной строке, сверху вниз."""
    full = [i for i, (_, row) in enumerate(rows) if sum(1 for c in row if c) * 2 >= width]
    if not full:
        return [row for _, row in rows]
    parts: dict[int, list[int]] = {i: [] for i in full}
    for i, (y, _) in enumerate(rows):
        owner = i if i in parts else min(full, key=lambda f: abs(rows[f][0] - y))
        parts[owner].append(i)
    merged = []
    for owner in full:
        row = [""] * width
        for i in sorted(parts[owner], key=lambda i: -rows[i][0]):  # сверху вниз
            for c, text in enumerate(rows[i][1]):
                if text:
                    row[c] = _join_cell(row[c], text)
        merged.append(row)
    return merged


def read_file(filename: str, data: bytes) -> tuple[list[list[str]] | None, str]:
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


def rows_from_table(rows: list[list[str]]) -> list[dict]:
    header, *body = rows
    mapping = {i: _field_for(h) for i, h in enumerate(header)}
    # «Title» рядом с именем и email — должность человека, а не вакансия
    # (у списка вакансий есть ссылка).
    if "link" not in mapping.values() and "position" not in mapping.values():
        mapping = {i: "position" if f == "title" else f for i, f in mapping.items()}
    if "email" not in mapping.values() and "company" not in mapping.values():
        raise ValueError(
            "Не нашёл столбцы «Компания» и «Email» — проверьте первую строку-заголовок."
        )
    result = []
    for number, row in enumerate(body, start=2):
        item = {f: "" for f in FIELDS}
        for i, value in enumerate(row):
            field = mapping.get(i)
            if field and value.strip() and not item[field]:
                item[field] = value.strip()
        # В ячейке бывает «hr@x.ru, careers@x.ru» — берём первый адрес.
        emails = extract_emails(item["email"]) if item["email"] else []
        item["email"] = emails[0] if emails else item["email"].lower()
        item["telegram"] = item["telegram"].replace("https://t.me/", "").lstrip("@")
        item["row"] = number
        if item["company"] or item["email"]:
            result.append(item)
    return result


CHUNK_CHARS = 6000  # столько текста за один запрос к LLM — большой PDF идёт частями


def _chunks(text: str) -> list[str]:
    """Режем по строкам, чтобы компания не разрывалась посередине."""
    chunks, current = [], ""
    lines = [
        piece
        for line in text.splitlines(keepends=True)
        for piece in (line[i:i + CHUNK_CHARS] for i in range(0, len(line), CHUNK_CHARS))
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
    text: str, llm_api_key: str, progress: Optional[Callable[[int, int], None]] = None
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
        name: str = Field(default="", description="Имя контакта/рекрутера, если есть")
        website: str = ""
        title: str = Field(default="", description="Вакансия, если упомянута")
        emphasis: str = Field(default="", description="На что сделать упор в письме")

    class _Companies(BaseModel):
        companies: list[_Company]

    prompt = ChatPromptTemplate.from_template(
        "Разложи список компаний из текста по полям. Бери только то, что "
        "написано в тексте, ничего не придумывай; поля без данных — пустые.\n\n{text}"
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
                _Companies, llm.with_structured_output(_Companies).invoke(prompt.format(text=part))
            ).companies
        except Exception as e:
            failed += 1
            from src.logging import logger

            logger.warning(f"Импорт: часть {index + 1}/{len(parts)} не разобрана LLM: {e}")
    if parts and failed == len(parts) and not extract_emails(text):
        raise ValueError("ИИ не смог разобрать файл — проверьте ключ ИИ или сохраните список как CSV/XLSX.")
    if progress:
        progress(len(parts), len(parts))
    source_emails = {e.lower() for e in extract_emails(text)}
    result = []
    for number, c in enumerate(parsed, start=1):
        email = c.email.strip().lower()
        item = {f: "" for f in FIELDS}
        item.update(
            company=c.company.strip(), name=c.name.strip(), website=c.website.strip(),
            title=c.title.strip(), emphasis=c.emphasis.strip(),
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
        name = labels[-3] if len(labels) > 2 and labels[-2] in ("co", "com", "org", "net", "ac") else labels[-2]
        item.update(email=email, website=domain, row=len(result) + 1, company=name.capitalize())
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


def preview(rows: list[dict], known_emails: set[str], written_emails: set[str]) -> dict:
    """Что будет импортировано: сводка и строки с пометками."""
    # Домены проверяем параллельно — иначе сотня адресов ждёт минуты.
    domains = {r["email"].split("@")[1].lower() for r in rows if "@" in r["email"]}
    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(domain_accepts_mail, domains - set(_MX_CACHE)))
    seen: set[str] = set()
    items = []
    stats = {"total": len(rows), "ok": 0, "bad": 0, "unknown": 0,
             "duplicate": 0, "already_written": 0}
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
