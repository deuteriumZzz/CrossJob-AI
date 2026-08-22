from __future__ import annotations

from pathlib import Path


def _format_yaml_scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def set_top_level_field(config_file: Path, key: str, value: str) -> None:
    """Точечно правит один плоский top-level YAML-ключ (например
    llm_api_key в secrets.yaml) — та же текстовая техника, что
    set_source_field, но для полей без вложенности в блок источника.
    Значение всегда строка в одинарных кавычках (единственный
    сегодняшний случай использования — API-ключи)."""
    text = config_file.read_text(encoding="utf-8")
    lines = text.splitlines()
    quoted = "'" + value.replace("'", "''") + "'"

    for index, line in enumerate(lines):
        if line.strip().startswith(f"{key}:") and not line.startswith(
            (" ", "\t")
        ):
            lines[index] = f"{key}: {quoted}"
            config_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return

    lines.insert(0, f"{key}: {quoted}")
    config_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def set_source_field(
    config_file: Path,
    source: str,
    key: str,
    value: object,
    quote: bool = False,
) -> None:
    """Точечно правит одно поле (bool/число/строка) внутри блока
    источника в work_preferences.yaml/secrets.yaml — текстовая правка
    одной строки, а не yaml.safe_dump всего файла, чтобы не терять
    комментарии (тот же подход, что уже main.
    append_to_company_blacklist использует для company_blacklist).
    quote=True для значений, которые могут содержать YAML-спецсимволы
    (API-ключи) — та же кавычечная техника, что set_top_level_field."""
    text = config_file.read_text(encoding="utf-8")
    lines = text.splitlines()
    value_text = (
        "'" + str(value).replace("'", "''") + "'"
        if quote
        else _format_yaml_scalar(value)
    )

    block_start = None
    for index, line in enumerate(lines):
        if line.strip() == f"{source}:" and not line.startswith((" ", "\t")):
            block_start = index
            break

    if block_start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(f"{source}:")
        lines.append(f"  {key}: {value_text}")
        config_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return

    block_end = len(lines)
    for index in range(block_start + 1, len(lines)):
        line = lines[index]
        if line.strip() and not line.startswith((" ", "\t")):
            block_end = index
            break

    for index in range(block_start + 1, block_end):
        stripped = lines[index].strip()
        if stripped.startswith(f"{key}:"):
            indent = lines[index][
                : len(lines[index]) - len(lines[index].lstrip())
            ]
            lines[index] = f"{indent}{key}: {value_text}"
            config_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return

    lines[block_end:block_end] = [f"  {key}: {value_text}"]
    config_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def set_list_field(config_file: Path, key: str, values: list[str]) -> None:
    """Заменяет ЦЕЛИКОМ top-level YAML-список (positions, locations,
    company_blacklist/title_blacklist/location_blacklist в
    work_preferences.yaml) — в отличие от set_source_field это не
    правка одного поля, а замена всего блока `- item` строк под
    ключом. Значения всегда в одинарных кавычках (та же техника, что
    set_top_level_field) — свободный ввод из дашборда (названия
    компаний/должностей) может содержать `:`/`#`, ломающие YAML без
    кавычек. Пустой список пишется как `key: []`, а не пустой блок —
    так уже принято в data_folder_example/work_preferences.yaml для
    "оставить пустым, чтобы вывести из резюме"."""
    text = config_file.read_text(encoding="utf-8")
    lines = text.splitlines()
    new_lines = [f"  - '{v.replace(chr(39), chr(39) * 2)}'" for v in values]

    block_start = None
    for index, line in enumerate(lines):
        if line.strip() == f"{key}:" or line.strip().startswith(f"{key}: "):
            block_start = index
            break

    if block_start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(f"{key}:" if new_lines else f"{key}: []")
        lines.extend(new_lines)
        config_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return

    block_end = block_start + 1
    for index in range(block_start + 1, len(lines)):
        if lines[index].strip().startswith("- "):
            block_end = index + 1
        else:
            break

    replacement = [f"{key}:" if new_lines else f"{key}: []"] + new_lines
    lines[block_start:block_end] = replacement
    config_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def set_source_list_field(
    config_file: Path, source: str, key: str, values: list[str]
) -> None:
    """Как set_list_field, но список вложен внутри блока источника
    (например telegram.channels — не верхнеуровневый ключ, а поле
    внутри telegram:), поэтому сначала находим границы блока
    источника (как set_source_field), а внутри них — сам список
    (индент на 2 больше, чем у ключа, как у set_list_field)."""
    text = config_file.read_text(encoding="utf-8")
    lines = text.splitlines()
    new_lines = [f"    - '{v.replace(chr(39), chr(39) * 2)}'" for v in values]

    block_start = None
    for index, line in enumerate(lines):
        if line.strip() == f"{source}:" and not line.startswith((" ", "\t")):
            block_start = index
            break

    if block_start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(f"{source}:")
        lines.append(f"  {key}:" if new_lines else f"  {key}: []")
        lines.extend(new_lines)
        config_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return

    block_end = len(lines)
    for index in range(block_start + 1, len(lines)):
        line = lines[index]
        if line.strip() and not line.startswith((" ", "\t")):
            block_end = index
            break

    key_start = None
    for index in range(block_start + 1, block_end):
        if lines[index].strip() == f"{key}:" or lines[
            index
        ].strip().startswith(f"{key}: "):
            key_start = index
            break

    if key_start is None:
        insertion = [f"  {key}:" if new_lines else f"  {key}: []"] + new_lines
        lines[block_end:block_end] = insertion
        config_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return

    key_end = key_start + 1
    for index in range(key_start + 1, block_end):
        if lines[index].strip().startswith("- "):
            key_end = index + 1
        else:
            break

    replacement = [f"  {key}:" if new_lines else f"  {key}: []"] + new_lines
    lines[key_start:key_end] = replacement
    config_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
