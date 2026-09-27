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
