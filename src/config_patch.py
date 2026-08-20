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
    config_file: Path, source: str, key: str, value: object
) -> None:
    """Точечно правит одно поле (bool/число) внутри блока источника в
    work_preferences.yaml — текстовая правка одной строки, а не
    yaml.safe_dump всего файла, чтобы не терять комментарии (тот же
    подход, что уже main.append_to_company_blacklist использует для
    company_blacklist)."""
    text = config_file.read_text(encoding="utf-8")
    lines = text.splitlines()
    value_text = _format_yaml_scalar(value)

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
