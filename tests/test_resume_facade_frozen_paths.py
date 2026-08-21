"""Регрессия: ResumeFacade вычисляла lib_directory через __file__,
что в PyInstaller-сборке (desktop_app.spec) не указывает на реальную
папку с забандленными prompt-шаблонами/стилями — они распакованы в
sys._MEIPASS. Без этого фикса генерация резюме/письма в собранном
.exe/.app падала бы на первом же обращении к прочитанным по прямому
пути strings.py (importlib.util.spec_from_file_location) — то же
семейство бага, что уже чинили в main._project_root()/StyleManager."""

import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from src.libs.resume_and_cover_builder.config import global_config
from src.libs.resume_and_cover_builder.resume_facade import ResumeFacade

LIB_DIR = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "libs"
    / "resume_and_cover_builder"
)
BUNDLED_SUBDIRS = [
    "resume_style",
    "resume_prompt",
    "resume_job_description_prompt",
    "cover_letter_prompt",
]


def _build_facade() -> None:
    ResumeFacade(
        api_key="sk-test",
        style_manager=MagicMock(),
        resume_generator=MagicMock(),
        resume_object=MagicMock(),
        output_path=Path(tempfile.gettempdir()),
    )


def test_resolves_prompt_and_style_paths_from_source_layout():
    _build_facade()
    cover_letter_path = (
        global_config.STRINGS_MODULE_COVER_LETTER_JOB_DESCRIPTION_PATH
    )
    assert global_config.STRINGS_MODULE_RESUME_PATH.exists()
    assert global_config.STRINGS_MODULE_RESUME_JOB_DESCRIPTION_PATH.exists()
    assert cover_letter_path.exists()
    assert global_config.STYLES_DIRECTORY.exists()


def test_resolves_prompt_and_style_paths_from_simulated_frozen_bundle(
    monkeypatch,
):
    with tempfile.TemporaryDirectory() as tmp:
        bundle = Path(tmp) / "bundle"
        dest_base = bundle / "src" / "libs" / "resume_and_cover_builder"
        for sub in BUNDLED_SUBDIRS:
            shutil.copytree(
                LIB_DIR / sub,
                dest_base / sub,
                ignore=shutil.ignore_patterns("__pycache__"),
            )

        monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
        _build_facade()

        cover_letter_path = (
            global_config.STRINGS_MODULE_COVER_LETTER_JOB_DESCRIPTION_PATH
        )
        assert global_config.STRINGS_MODULE_RESUME_PATH.exists()
        assert (
            global_config.STRINGS_MODULE_RESUME_JOB_DESCRIPTION_PATH.exists()
        )
        assert cover_letter_path.exists()
        assert global_config.STYLES_DIRECTORY.exists()
        assert str(bundle) in str(global_config.STRINGS_MODULE_RESUME_PATH)
