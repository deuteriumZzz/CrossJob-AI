"""Регрессия: два module-level пути, вычисляемые через голый
__file__ при импорте, что в PyInstaller-сборке (desktop_app.spec) не
указывает на реальные забандленные файлы — они распакованы в
sys._MEIPASS.

_LIB_DIR (cover_letter.py) — самый критичный путь во всём этом
семействе багов: используется generate_cover_letter_for_job(),
вызываемой при каждом отклике на КАЖДОЙ площадке, а не только из
кнопок дашборда. Без фикса — ни одно сопроводительное письмо не
сгенерировалось бы в собранном .exe/.app.

STATIC_DIR (src/webui/api.py) — если бы не резолвился, `if
STATIC_DIR.exists(): app.mount(...)` в конце файла молча не
подключил бы статику: пустое окно дашборда без единой ошибки в логах.
"""

import importlib
import shutil
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_lib_dir_resolves_from_simulated_frozen_bundle(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        bundle = Path(tmp) / "bundle"
        shutil.copytree(
            PROJECT_ROOT
            / "src"
            / "libs"
            / "resume_and_cover_builder"
            / "cover_letter_prompt",
            bundle
            / "src"
            / "libs"
            / "resume_and_cover_builder"
            / "cover_letter_prompt",
            ignore=shutil.ignore_patterns("__pycache__"),
        )

        monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
        import src.job_sources.cover_letter as cover_letter_module

        try:
            importlib.reload(cover_letter_module)
            strings_path = (
                cover_letter_module._LIB_DIR
                / "cover_letter_prompt"
                / "strings.py"
            )
            assert strings_path.exists()
            assert str(bundle) in str(cover_letter_module._LIB_DIR)
        finally:
            monkeypatch.delattr(sys, "_MEIPASS", raising=False)
            importlib.reload(cover_letter_module)


def test_static_dir_resolves_from_simulated_frozen_bundle(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        bundle = Path(tmp) / "bundle"
        shutil.copytree(
            PROJECT_ROOT / "src" / "webui" / "static",
            bundle / "src" / "webui" / "static",
            ignore=shutil.ignore_patterns("__pycache__"),
        )

        monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
        import src.webui.api as api_module

        try:
            importlib.reload(api_module)
            assert api_module.STATIC_DIR.exists()
            assert str(bundle) in str(api_module.STATIC_DIR)
        finally:
            monkeypatch.delattr(sys, "_MEIPASS", raising=False)
            importlib.reload(api_module)
