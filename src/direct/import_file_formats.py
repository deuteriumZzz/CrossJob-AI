"""Format-specific readers for company/contact imports."""

from __future__ import annotations

import csv
import io
import posixpath
import re
import zipfile
from typing import Callable
from xml.etree import ElementTree as ET

_XLSX_MAIN_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_XLSX_REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_PACKAGE_REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_MAX_ARCHIVE_FILES = 2_000
_MAX_ARCHIVE_EXPANDED_BYTES = 100 * 1024 * 1024
_MAX_XLSX_ROWS_PER_SHEET = 100_000
_MAX_XLSX_CELLS_PER_SHEET = 1_000_000
_MAX_XLSX_COLUMNS = 1_024


class ParsedTable(list[list[str]]):
    """Rows plus non-fatal notes about sheets omitted from an import."""

    def __init__(self, rows: list[list[str]], warnings: list[str] | None = None):
        super().__init__(rows)
        self.warnings = warnings or []


def _check_archive(z: zipfile.ZipFile) -> None:
    members = z.infolist()
    if len(members) > _MAX_ARCHIVE_FILES:
        raise ValueError("В архиве слишком много элементов для безопасного разбора.")
    if sum(member.file_size for member in members) > _MAX_ARCHIVE_EXPANDED_BYTES:
        raise ValueError("Файл слишком сложный или большой после распаковки.")


def _xlsx_sheet_rows(
    z: zipfile.ZipFile, sheet_path: str, shared: list[str]
) -> list[list[str]]:
    if sheet_path not in z.namelist():
        return []
    rows: list[list[str]] = []
    cell_count = 0
    root = ET.fromstring(z.read(sheet_path))
    for row in root.iter(f"{_XLSX_MAIN_NS}row"):
        values: dict[int, str] = {}
        for cell in row.iter(f"{_XLSX_MAIN_NS}c"):
            ref = re.match(r"[A-Z]+", cell.get("r", "A"))
            letters = ref.group(0) if ref else "A"
            column = 0
            for character in letters:
                column = column * 26 + ord(character) - 64
            if column > _MAX_XLSX_COLUMNS:
                raise ValueError("В таблице Excel слишком много столбцов.")
            cell_count += 1
            if cell_count > _MAX_XLSX_CELLS_PER_SHEET:
                raise ValueError("В листе Excel слишком много ячеек для импорта.")
            value_node = cell.find(f"{_XLSX_MAIN_NS}v")
            inline = cell.find(f".//{_XLSX_MAIN_NS}t")
            if cell.get("t") == "s" and value_node is not None:
                try:
                    value = shared[int(value_node.text or 0)]
                except (ValueError, IndexError):
                    value = ""
            elif inline is not None:
                value = inline.text or ""
            else:
                value = (
                    value_node.text
                    if value_node is not None and value_node.text
                    else ""
                )
            values[column - 1] = value
        if values:
            rows.append([values.get(index, "") for index in range(max(values) + 1)])
            if len(rows) > _MAX_XLSX_ROWS_PER_SHEET:
                raise ValueError("В листе Excel больше 100 000 строк.")
    return rows


def _skipped_content_warning(names: list[str]) -> list[str]:
    if not names:
        return []
    preview = ", ".join(names[:5])
    suffix = " и другие" if len(names) > 5 else ""
    return [
        f"Не удалось автоматически распознать таблицу в: {preview}{suffix}. Проверьте, что нужные данные попали в предпросмотр."
    ]


def _canonical_rows(items: list[dict], fields: tuple[str, ...]) -> list[list[str]]:
    return [[str(item.get(field, "") or "") for field in fields] for item in items]


def _xlsx_rows(
    data: bytes,
    fields: tuple[str, ...],
    table_mapping: Callable,
    rows_from_table: Callable,
) -> ParsedTable:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        _check_archive(z)
        names = set(z.namelist())
        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            shared_root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            shared = [
                "".join(node.text or "" for node in item.iter(f"{_XLSX_MAIN_NS}t"))
                for item in shared_root.iter(f"{_XLSX_MAIN_NS}si")
            ]
        workbook_path = "xl/workbook.xml"
        rels_path = "xl/_rels/workbook.xml.rels"
        if workbook_path not in names or rels_path not in names:
            raise ValueError("Не удалось прочитать структуру листов Excel.")
        workbook = ET.fromstring(z.read(workbook_path))
        relationships = ET.fromstring(z.read(rels_path))
        targets = {
            item.get("Id", ""): item.get("Target", "")
            for item in relationships.iter(f"{_PACKAGE_REL_NS}Relationship")
        }
        sheets: list[tuple[str, list[list[str]]]] = []
        for sheet in workbook.iter(f"{_XLSX_MAIN_NS}sheet"):
            target = targets.get(sheet.get(f"{_XLSX_REL_NS}id", ""), "")
            if not target:
                continue
            sheet_path = (
                target.lstrip("/")
                if target.startswith("/")
                else posixpath.normpath(posixpath.join("xl", target))
            )
            if not sheet_path.startswith("xl/worksheets/"):
                continue
            rows = _xlsx_sheet_rows(z, sheet_path, shared)
            if rows:
                sheets.append((sheet.get("name", sheet_path), rows))

    if not sheets:
        raise ValueError("В книге Excel нет непустых листов.")
    usable: list[tuple[str, list[list[str]]]] = []
    skipped: list[str] = []
    for name, rows in sheets:
        try:
            table_mapping(rows)
            mapped = rows_from_table(rows)
        except (ValueError, KeyError, IndexError):
            skipped.append(name)
            continue
        if any(item.get("company") or item.get("email") for item in mapped):
            usable.append((name, mapped))
        else:
            skipped.append(name)

    if not usable:
        # Keep custom headers intact so the UI can offer manual column mapping.
        best_name, best_rows = max(sheets, key=lambda item: len(item[1]))
        skipped.extend(name for name, _ in sheets if name != best_name)
        warnings = [
            f"На листе «{best_name}» не удалось уверенно определить столбцы. "
            "Проверьте и задайте их вручную в блоке сопоставления."
        ]
        return ParsedTable(best_rows, warnings + _skipped_content_warning(skipped))
    if len(usable) == 1:
        selected = usable[0][0]
        skipped.extend(
            name for name, _ in sheets if name != selected and name not in skipped
        )
        selected_rows = next(rows for name, rows in sheets if name == selected)
        return ParsedTable(selected_rows, _skipped_content_warning(skipped))

    combined = [list(fields)]
    for _, items in usable:
        combined.extend(_canonical_rows(items, fields))
    usable_names = {name for name, _ in usable}
    skipped.extend(
        name for name, _ in sheets if name not in usable_names and name not in skipped
    )
    return ParsedTable(combined, _skipped_content_warning(skipped))


def _decode(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
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
    return [
        row
        for row in csv.reader(io.StringIO(text), dialect)
        if any(cell.strip() for cell in row)
    ]


def _docx_content(data: bytes) -> tuple[list[list[list[str]]], str]:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        _check_archive(z)
        if "word/document.xml" not in z.namelist():
            raise ValueError("Не найден основной текст Word-документа.")
        root = ET.fromstring(z.read("word/document.xml"))
    w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    body = root.find(f"{w}body")
    if body is None:
        return [], ""
    tables: list[list[list[str]]] = []
    text_lines: list[str] = []
    for block in body:
        if block.tag == f"{w}p":
            text = "".join(node.text or "" for node in block.iter(f"{w}t")).strip()
            if text:
                text_lines.append(text)
            continue
        if block.tag != f"{w}tbl":
            continue
        rows: list[list[str]] = []
        for row in block.findall(f"{w}tr"):
            cells = [
                " ".join(
                    "".join(node.text or "" for node in paragraph.iter(f"{w}t")).strip()
                    for paragraph in cell.findall(f"{w}p")
                ).strip()
                for cell in row.findall(f"{w}tc")
            ]
            if any(cells):
                rows.append(cells)
                text_lines.append("\t".join(cells))
        if rows:
            tables.append(rows)
        text_lines.append("")
    return tables, "\n".join(text_lines)


def _docx_rows(
    data: bytes,
    fields: tuple[str, ...],
    rows_from_table: Callable,
) -> ParsedTable | None:
    tables, _ = _docx_content(data)
    if not tables:
        return None
    usable: list[tuple[int, list[list[str]]]] = []
    skipped: list[str] = []
    for index, rows in enumerate(tables, start=1):
        try:
            mapped = rows_from_table(rows)
        except (ValueError, KeyError, IndexError):
            skipped.append(f"таблица {index}")
            continue
        if any(item.get("company") or item.get("email") for item in mapped):
            usable.append((index, mapped))
        else:
            skipped.append(f"таблица {index}")
    if not usable:
        best_index, best_rows = max(
            enumerate(tables, start=1), key=lambda item: len(item[1])
        )
        skipped.extend(
            f"таблица {index}"
            for index in range(1, len(tables) + 1)
            if index != best_index
        )
        warnings = [
            f"В таблице {best_index} Word не удалось уверенно определить столбцы. "
            "Проверьте и задайте их вручную в блоке сопоставления."
        ]
        return ParsedTable(best_rows, warnings + _skipped_content_warning(skipped))
    if len(usable) == 1:
        index = usable[0][0]
        skipped.extend(
            f"таблица {other}"
            for other in range(1, len(tables) + 1)
            if other != index and f"таблица {other}" not in skipped
        )
        return ParsedTable(tables[index - 1], _skipped_content_warning(skipped))
    combined = [list(fields)]
    for _, items in usable:
        combined.extend(_canonical_rows(items, fields))
    usable_indexes = {index for index, _ in usable}
    skipped.extend(
        f"таблица {index}"
        for index in range(1, len(tables) + 1)
        if index not in usable_indexes and f"таблица {index}" not in skipped
    )
    return ParsedTable(combined, _skipped_content_warning(skipped))


def _docx_text(data: bytes) -> str:
    return _docx_content(data)[1]


def _markdown_rows(text: str) -> list[list[str]] | None:
    rows = [
        [cell.strip().strip("`") for cell in line.strip().strip("|").split("|")]
        for line in text.splitlines()
        if line.strip().startswith("|") and not re.fullmatch(r"[\s|:-]+", line)
    ]
    return rows if len(rows) > 1 else None


def _delimited_text_rows(text: str) -> list[list[str]] | None:
    """Recognize plain-text tables only when their row shape is consistent."""
    candidates: list[tuple[float, list[list[str]]]] = []
    for delimiter in ("\t", ";", "|", ","):
        parsed = [
            [cell.strip().strip("`") for cell in row]
            for row in csv.reader(io.StringIO(text), delimiter=delimiter)
            if any(cell.strip() for cell in row)
        ]
        if len(parsed) < 2:
            continue
        widths = [len(row) for row in parsed]
        common_width = max(set(widths), key=widths.count)
        if common_width < 2:
            continue
        consistency = widths.count(common_width) / len(widths)
        if consistency >= 0.7:
            candidates.append((consistency * min(common_width, 10), parsed))
    if not candidates:
        return None
    return max(candidates, key=lambda candidate: candidate[0])[1]


def _pdf_table_rows(data: bytes, field_for: Callable) -> list[list[str]] | None:
    """Extract text PDF tables by cell coordinates, without assigning emails to the wrong row."""
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
            key=lambda item: -item[0],
        )
        groups: list[list[tuple[float, float, str]]] = []
        for line in lines:
            if groups and groups[-1][0][0] - line[0] < 2:
                groups[-1].append(line)
            else:
                groups.append([line])
        for group in groups:
            cells = sorted((x, text) for _, x, text in group)
            texts = [text for _, text in cells]
            if not header:
                fields = {field_for(text) for text in texts}
                if "email" in fields and ({"company", "name"} & fields):
                    header, centers = texts, [x for x, _ in cells]
                continue
            if texts == header:
                continue
            row = [""] * len(header)
            for x, text in cells:
                column = min(
                    range(len(centers)), key=lambda index: abs(centers[index] - x)
                )
                row[column] = (
                    row[column]
                    + ("" if row[column].endswith((".", "@", "-", "_")) else " ")
                    + text
                    if row[column]
                    else text
                )
            page_rows.append((group[0][0], row))
        rows.extend(_merge_wrapped(page_rows, len(header)))
        page_rows = []
    return [header, *rows] if header and rows else None


def _pdf_page_text(data: bytes) -> list[str]:
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTTextContainer

    return [
        "\n".join(
            box.get_text().strip()
            for box in page
            if isinstance(box, LTTextContainer) and box.get_text().strip()
        )
        for page in extract_pages(io.BytesIO(data))
    ]


def _merge_wrapped(rows: list[tuple[float, list[str]]], width: int) -> list[list[str]]:
    full = [
        index
        for index, (_, row) in enumerate(rows)
        if sum(bool(cell) for cell in row) * 2 >= width
    ]
    if not full:
        return [row for _, row in rows]
    parts: dict[int, list[int]] = {index: [] for index in full}
    for index, (y, _) in enumerate(rows):
        owner = (
            index
            if index in parts
            else min(full, key=lambda full_index: abs(rows[full_index][0] - y))
        )
        parts[owner].append(index)
    merged = []
    for owner in full:
        row = [""] * width
        for index in sorted(parts[owner], key=lambda item: -rows[item][0]):
            for column, text in enumerate(rows[index][1]):
                if text:
                    previous = row[column]
                    row[column] = (
                        previous
                        + ("" if previous.endswith((".", "@", "-", "_")) else " ")
                        + text
                        if previous
                        else text
                    )
        merged.append(row)
    return merged


def read_import_file(
    filename: str,
    data: bytes,
    *,
    fields: tuple[str, ...],
    field_for: Callable,
    table_mapping: Callable,
    rows_from_table: Callable,
    on_ocr_progress: Callable[[int, int], None] | None = None,
) -> tuple[list[list[str]] | None, str]:
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext == "md":
        text = _decode(data)
        return _markdown_rows(text) or _delimited_text_rows(text), text
    if ext == "xlsx":
        return _xlsx_rows(data, fields, table_mapping, rows_from_table), ""
    if ext in ("csv", "tsv"):
        return _csv_rows(data), ""
    if ext == "docx":
        table = _docx_rows(data, fields, rows_from_table)
        return (table, "") if table else (None, _docx_text(data))
    if ext == "pdf":
        pages = _pdf_page_text(data)
        if not pages:
            return None, ""
        text_pages = [
            index + 1
            for index, page_text in enumerate(pages)
            if len(re.sub(r"\s", "", page_text)) < 25
        ]
        if text_pages:
            from src.direct.pdf_ocr import recognize_pdf_pages

            recognized = recognize_pdf_pages(
                data, text_pages, on_progress=on_ocr_progress
            )
            pages = [
                (
                    recognized.get(index + 1, "").strip() or page_text
                    if index + 1 in text_pages
                    else page_text
                )
                for index, page_text in enumerate(pages)
            ]
            return None, "\n\n".join(page for page in pages if page.strip())
        table = _pdf_table_rows(data, field_for)
        if table:
            return table, ""
        return None, "\n\n".join(page for page in pages if page.strip())
    if ext == "txt":
        text = _decode(data)
        return _delimited_text_rows(text), text
    return None, _decode(data)
