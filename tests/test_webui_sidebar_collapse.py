from pathlib import Path


STATIC_DIR = Path(__file__).parents[1] / "src" / "webui" / "static"


def test_sidebar_collapse_does_not_overflow_or_flash_on_startup():
    css = (STATIC_DIR / "style.css").read_text(encoding="utf-8")
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert ".sidebar.collapsed .activity" in css
    assert ".sidebar.is-transitioning .activity" in css
    assert ".sidebar.is-transitioning .brand-text" in css
    assert ".sidebar.is-transitioning .theme-toggle" in css
    assert "function restoreSidebarCollapse()" in script
    assert "sidebar.classList.add(\"is-transitioning\");" in script
    assert "restoreSidebarCollapse();\n  document.getElementById(\"app-shell\").style.display = \"\";" in script

    brand_name_rules = css.split(".brand-name {", 1)[1].split("}", 1)[0]
    assert "white-space: nowrap;" in brand_name_rules
