"""Автопроверка «ничего не потерялось» (docs/PLAN.md, раздел F, добавка 3).

Каждая функция интерфейса записана в docs/UI_MAP.md ключом. Для частей,
которые уже перенесены в новый вид, у элемента должна быть метка
data-ui="<ключ>" (в шаблонах app.js — ui: "<ключ>").
"""

import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
UI_MAP = ROOT / "docs" / "UI_MAP.md"
STATIC = ROOT / "src" / "webui" / "static"

KEY_ROW = re.compile(r"^\| `([a-z0-9][a-z0-9.\-]*)` \|", re.M)


def _sections(text: str) -> dict[str, str]:
    """Номер раздела карты («1», «2», …) → его текст."""
    parts = re.split(r"^## (\d+)\. ", text, flags=re.M)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts) - 1, 2)}


def _migrated_sections(text: str) -> set[str]:
    status = text.split("## Статус переноса", 1)[1].split("\n## ", 1)[0]
    done: set[str] = set()
    for line in status.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 4 and cells[3] == "перенесён":
            done |= {n.strip() for n in cells[1].split(",") if n.strip()}
    return done - {"—"}


def _markers() -> set[str]:
    source = "\n".join(
        (STATIC / name).read_text(encoding="utf-8")
        for name in ("index.html", "app.js")
    )
    found: set[str] = set()
    for pattern in (r'data-ui="([^"$]+)"', r'\bui: "([^"]+)"'):
        for value in re.findall(pattern, source):
            found |= set(value.split())
    return found


def test_ui_map_keys_are_unique():
    text = UI_MAP.read_text(encoding="utf-8")
    keys = []
    for number, body in _sections(text).items():
        if number in {str(n) for n in range(1, 10)}:
            keys += KEY_ROW.findall(body)
    duplicates = sorted({k for k in keys if keys.count(k) > 1})
    assert not duplicates, f"повторяются ключи: {duplicates}"


def test_every_migrated_function_has_its_marker():
    text = UI_MAP.read_text(encoding="utf-8")
    sections = _sections(text)
    migrated = _migrated_sections(text)
    assert migrated, "в таблице «Статус переноса» нет перенесённых частей"
    markers = _markers()
    missing = [
        f"{number}: {key}"
        for number in sorted(migrated, key=int)
        for key in KEY_ROW.findall(sections[number])
        if key not in markers
    ]
    assert not missing, "нет метки data-ui у: " + ", ".join(missing)
