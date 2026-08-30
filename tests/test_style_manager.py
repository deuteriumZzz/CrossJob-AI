"""Регрессия: StyleManager искала resume_style/ через __file__, что
в PyInstaller-сборке (desktop_app.spec) не указывает на реальную
папку с забандленными CSS — они распакованы в sys._MEIPASS. Без этого
фикса собранный .exe/.app показывал бы "No styles available" (пустой
StyleManager.get_styles()) на кнопках генерации резюме в дашборде."""

import shutil
import sys
import tempfile
from pathlib import Path

from src.libs.resume_and_cover_builder.style_manager import (
    StyleManager,
    analyze_ats_risks,
)

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


def test_analyze_ats_risks_flags_grid_entry_columns():
    css = """
    .entry {
      display: grid;
      grid-template-columns: 1fr 4fr;
    }
    """
    risks = analyze_ats_risks(css)
    assert any("Опыт работы" in r for r in risks)


def test_analyze_ats_risks_flags_flex_row_two_column_skills():
    css = """
    .two-column {
      display: flex;
      justify-content: space-between;
    }
    """
    risks = analyze_ats_risks(css)
    assert any("Навыки" in r for r in risks)


def test_analyze_ats_risks_ignores_single_column_flex():
    # flex-direction: column укладывает детей друг под другом — не
    # колонки, а обычный вертикальный стек, риска нет.
    css = """
    .entry {
      display: flex;
      flex-direction: column;
    }
    .two-column {
      display: flex;
      flex-direction: column;
    }
    """
    assert analyze_ats_risks(css) == []


def test_analyze_ats_risks_flags_icon_only_contacts():
    css = """
    .contact-info {
      display: flex;
    }
    .contact-info p {
      margin: 0;
    }
    """
    risks = analyze_ats_risks(css)
    assert any("иконками" in r for r in risks)


def test_analyze_ats_risks_accepts_contact_text_fallback():
    css = """
    .contact-info p:nth-child(1)::before {
      content: "address:";
    }
    """
    risks = analyze_ats_risks(css)
    assert not any("иконками" in r for r in risks)


def test_analyze_ats_risks_does_not_match_entry_header_prefix():
    # .entry-header не должен считаться селектором .entry — иначе
    # каждый стиль (у всех есть .entry-header с display:flex) ложно
    # получит риск "Опыт работы в несколько колонок".
    css = """
    .entry-header {
      display: flex;
    }
    """
    assert analyze_ats_risks(css) == []


def test_get_ats_report_matches_known_real_style_risks():
    """Регрессия по реальным стилям — если кто-то поправит CSS одного
    из них, тест должен заметить смену риск-профиля, а не молчать."""
    report = StyleManager().get_ats_report()
    assert report["Clean Blue"]  # 2-колоночные .entry и .two-column
    assert report["Modern Grey"]  # только иконки-контакты
    assert len(report["Modern Grey"]) == 1
    assert len(report["Clean Blue"]) == 2
