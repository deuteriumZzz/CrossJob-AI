"""Регрессия: StyleManager искала resume_style/ через __file__, что
в PyInstaller-сборке (desktop_app.spec) не указывает на реальную
папку с забандленными CSS — они распакованы в sys._MEIPASS. Без этого
фикса собранный .exe/.app показывал бы "No styles available" (пустой
StyleManager.get_styles()) на кнопках генерации резюме в дашборде."""

import shutil
import sys
import tempfile
from pathlib import Path

from src.libs.resume_and_cover_builder.style_manager import StyleManager

REAL_STYLES_DIR = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "libs"
    / "resume_and_cover_builder"
    / "resume_style"
)


def test_finds_styles_from_source_layout():
    styles = StyleManager().get_styles()
    assert "Default" in styles


def test_finds_styles_from_simulated_frozen_bundle(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        bundle = Path(tmp) / "bundle"
        dest = (
            bundle
            / "src"
            / "libs"
            / "resume_and_cover_builder"
            / "resume_style"
        )
        dest.mkdir(parents=True)
        for css_file in REAL_STYLES_DIR.glob("*.css"):
            shutil.copy(css_file, dest / css_file.name)

        monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
        styles = StyleManager().get_styles()

        assert len(styles) == len(list(REAL_STYLES_DIR.glob("*.css")))
        assert "Default" in styles
