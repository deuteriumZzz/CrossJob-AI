from __future__ import annotations

import json
import os
import shutil
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import yaml


class ConfigWriteError(ValueError):
    """Настройки нельзя безопасно сохранить в YAML."""


def _backup_path(config_file: Path) -> Path:
    return config_file.with_suffix(f"{config_file.suffix}.bak")


_STAGED_FILES: set[Path] = set()


@contextmanager
def stage_config_updates(config_file: Path) -> Iterator[Path]:
    """Применяет несколько настроек как одну атомарную операцию.

    Обработчик API правит временную копию. Если хотя бы одно поле не
    проходит YAML-проверку, исходный файл не меняется. При успехе создаётся
    одна резервная копия версии до всего запроса, а не после каждого поля.
    """
    fd, name = tempfile.mkstemp(
        dir=config_file.parent,
        prefix=f".{config_file.name}.",
        suffix=".stage",
    )
    os.close(fd)
    staged = Path(name)
    shutil.copy2(config_file, staged)
    _STAGED_FILES.add(staged)
    try:
        yield staged
        _write_valid_yaml(config_file, staged.read_text(encoding="utf-8"))
    finally:
        _STAGED_FILES.discard(staged)
        staged.unlink(missing_ok=True)
        _backup_path(staged).unlink(missing_ok=True)


def _write_valid_yaml(config_file: Path, text: str) -> None:
    """Проверяет и атомарно сохраняет YAML с копией предыдущей версии.

    Главный файл заменяется только после успешного разбора нового текста.
    Перед заменой предыдущая корректная версия попадает в `.bak`; при
    ошибке разбора или сбое записи исходный файл остаётся нетронутым.
    """
    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigWriteError(
            f"Refusing to write invalid YAML to {config_file}: {exc}"
        ) from exc
    if not isinstance(parsed, dict):
        raise ConfigWriteError(
            f"Refusing to write invalid YAML to {config_file}: "
            "root must be a mapping"
        )

    parent = config_file.parent
    mode = stat.S_IMODE(config_file.stat().st_mode)
    temp_fd, temp_name = tempfile.mkstemp(
        dir=parent, prefix=f".{config_file.name}.", suffix=".tmp"
    )
    needs_backup = config_file not in _STAGED_FILES
    backup_temp_path = None
    if needs_backup:
        backup_fd, backup_name = tempfile.mkstemp(
            dir=parent, prefix=f".{config_file.name}.", suffix=".bak.tmp"
        )
        os.close(backup_fd)
        backup_temp_path = Path(backup_name)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp_path, mode)
        if needs_backup and backup_temp_path is not None:
            shutil.copy2(config_file, backup_temp_path)
            os.replace(backup_temp_path, _backup_path(config_file))
        os.replace(temp_path, config_file)
    except OSError as exc:
        raise ConfigWriteError(
            f"Could not safely save YAML file {config_file}: {exc}"
        ) from exc
    finally:
        temp_path.unlink(missing_ok=True)
        if backup_temp_path is not None:
            backup_temp_path.unlink(missing_ok=True)


def _format_yaml_scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _field_end(lines: list[str], field_start: int, block_end: int) -> int:
    """Возвращает конец значения YAML-поля внутри уже найденного блока.

    Тело значения — все следующие строки с более глубоким отступом: у
    folded/literal scalar-а (`>-`, `|`), но и у обычной строки, перенесённой
    на следующую строку (`key: Здравствуйте!` + `    Если позиция…` — так
    пишут руками). При замене заголовка надо заменить и тело: иначе в файле
    остаются «осиротевшие» строки, YAML перестаёт парситься и сохранение
    из UI падает целиком — вместе со всеми остальными полями раздела.
    Пустые строки после значения не трогаем — они разделители, не тело.
    """
    line = lines[field_start]
    field_indent = len(line) - len(line.lstrip())
    field_end = field_start + 1
    for index in range(field_start + 1, block_end):
        candidate = lines[index]
        if not candidate.strip():
            continue
        if len(candidate) - len(candidate.lstrip()) <= field_indent:
            break
        field_end = index + 1
    return field_end


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
            _write_valid_yaml(config_file, "\n".join(lines) + "\n")
            return

    lines.insert(0, f"{key}: {quoted}")
    _write_valid_yaml(config_file, "\n".join(lines) + "\n")


def set_top_level_bool_field(
    config_file: Path, key: str, value: bool | int
) -> None:
    """Как set_top_level_field, но для булевых top-level ключей
    (remote/hybrid/onsite в work_preferences.yaml) — без кавычек,
    той же текстовой техникой."""
    text = config_file.read_text(encoding="utf-8")
    lines = text.splitlines()
    value_text = _format_yaml_scalar(value)

    for index, line in enumerate(lines):
        if line.strip().startswith(f"{key}:") and not line.startswith(
            (" ", "\t")
        ):
            lines[index] = f"{key}: {value_text}"
            _write_valid_yaml(config_file, "\n".join(lines) + "\n")
            return

    lines.insert(0, f"{key}: {value_text}")
    _write_valid_yaml(config_file, "\n".join(lines) + "\n")


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
        (
            json.dumps(str(value), ensure_ascii=False)
            if "\n" in str(value)
            else "'" + str(value).replace("'", "''") + "'"
        )
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
        _write_valid_yaml(config_file, "\n".join(lines) + "\n")
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
            field_end = _field_end(lines, index, block_end)
            lines[index:field_end] = [f"{indent}{key}: {value_text}"]
            _write_valid_yaml(config_file, "\n".join(lines) + "\n")
            return

    lines[block_end:block_end] = [f"  {key}: {value_text}"]
    _write_valid_yaml(config_file, "\n".join(lines) + "\n")


def unset_source_field(config_file: Path, source: str, key: str) -> None:
    """Удаляет одно поле из блока источника, если оно там явно
    задано — обратная операция к set_source_field. Нужна для
    override-чекбоксов дневного лимита/лимита за прогон в дашборде:
    "своё значение для площадки" выключили — площадка должна снова
    наследовать общий дефолт, а не просто перестать редактироваться
    в UI, храня старое явное число в YAML. Молча ничего не делает,
    если блока или поля нет — сброс несуществующего override и так
    уже "сброшен"."""
    text = config_file.read_text(encoding="utf-8")
    lines = text.splitlines()

    block_start = None
    for index, line in enumerate(lines):
        if line.strip() == f"{source}:" and not line.startswith((" ", "\t")):
            block_start = index
            break
    if block_start is None:
        return

    block_end = len(lines)
    for index in range(block_start + 1, len(lines)):
        line = lines[index]
        if line.strip() and not line.startswith((" ", "\t")):
            block_end = index
            break

    for index in range(block_start + 1, block_end):
        if lines[index].strip().startswith(f"{key}:"):
            del lines[index]
            _write_valid_yaml(config_file, "\n".join(lines) + "\n")
            return


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
        _write_valid_yaml(config_file, "\n".join(lines) + "\n")
        return

    block_end = block_start + 1
    for index in range(block_start + 1, len(lines)):
        if lines[index].strip().startswith("- "):
            block_end = index + 1
        else:
            break

    replacement = [f"{key}:" if new_lines else f"{key}: []"] + new_lines
    lines[block_start:block_end] = replacement
    _write_valid_yaml(config_file, "\n".join(lines) + "\n")


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
        _write_valid_yaml(config_file, "\n".join(lines) + "\n")
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
        _write_valid_yaml(config_file, "\n".join(lines) + "\n")
        return

    key_end = key_start + 1
    for index in range(key_start + 1, block_end):
        if lines[index].strip().startswith("- "):
            key_end = index + 1
        else:
            break

    replacement = [f"  {key}:" if new_lines else f"  {key}: []"] + new_lines
    lines[key_start:key_end] = replacement
    _write_valid_yaml(config_file, "\n".join(lines) + "\n")
