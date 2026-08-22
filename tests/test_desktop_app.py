"""Регрессия: desktop_app.py раньше проверял data_folder ДО открытия
окна (sys.exit(1), если его нет) и опрашивал готовность сервера через
/api/status, который теперь требует настроенный data_folder (иначе
428) — на первом запуске готовность никогда бы не подтвердилась.
Оба места чинили одновременно с веб-визардом (POST /api/setup/init)."""

import httpx
import pytest

pytest.importorskip(
    "webview",
    reason=(
        "pywebview needs system GTK/WebKit libraries to import on "
        "Linux (pip alone doesn't provide them) — not installed on "
        "CI runners, same reason langchain-groq/etc. are importorskip'd."
    ),
)

import desktop_app  # noqa: E402


def test_wait_until_ready_succeeds_once_endpoint_responds_ok(monkeypatch):
    calls = {"count": 0}

    def fake_get(url, timeout):
        calls["count"] += 1
        response = httpx.Response(200, request=httpx.Request("GET", url))
        return response

    monkeypatch.setattr(httpx, "get", fake_get)
    desktop_app._wait_until_ready("http://127.0.0.1:1/api/setup/status")
    assert calls["count"] == 1


def test_wait_until_ready_raises_after_timeout(monkeypatch):
    def fake_get(url, timeout):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "get", fake_get)
    with pytest.raises(RuntimeError):
        desktop_app._wait_until_ready(
            "http://127.0.0.1:1/api/setup/status", timeout=0.3
        )


def test_main_probes_setup_status_not_status(monkeypatch):
    """main() must never poll /api/status directly — it 428s until
    data_folder is set up, so readiness would never be confirmed."""
    probed_urls = []

    monkeypatch.setattr(desktop_app, "_free_port", lambda: 1)

    class _FakeServer:
        should_exit = False

        def run(self):
            pass

    monkeypatch.setattr(
        desktop_app.uvicorn, "Config", lambda *a, **k: object()
    )
    monkeypatch.setattr(
        desktop_app.uvicorn, "Server", lambda *a, **k: _FakeServer()
    )

    def fake_wait_until_ready(url, timeout=15.0):
        probed_urls.append(url)

    monkeypatch.setattr(
        desktop_app, "_wait_until_ready", fake_wait_until_ready
    )
    monkeypatch.setattr(
        desktop_app.webview, "create_window", lambda *a, **k: None
    )
    monkeypatch.setattr(desktop_app.webview, "start", lambda: None)

    desktop_app.main()

    assert len(probed_urls) == 1
    assert probed_urls[0].endswith("api/setup/status")
