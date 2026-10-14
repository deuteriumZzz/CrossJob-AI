from pathlib import Path

STATIC_DIR = Path(__file__).parents[1] / "src" / "webui" / "static"


def test_telegram_channel_editor_exposes_paste_add_and_removable_list():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert 'id="tg-channel-input"' in html
    assert 'id="tg-channel-paste"' in html
    assert 'id="tg-channel-add"' in html
    assert 'id="tg-channel-list"' in html
    assert "navigator.clipboard.readText" in script
    assert "renderTelegramChannelList" in script


def test_nested_telegram_autosave_groups_do_not_show_duplicate_toasts():
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert "function isNestedAutosaveTarget(pane, target)" in script
    assert "if (isNestedAutosaveTarget(pane, e.target)) return;" in script
    assert "if (isNestedAutosaveTarget(container, el)) return;" in script
