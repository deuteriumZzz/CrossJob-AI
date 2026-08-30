"""Регрессия: desktop_app.py раньше проверял data_folder ДО открытия
окна (sys.exit(1), если его нет) и опрашивал готовность сервера через
/api/status, который теперь требует настроенный data_folder (иначе
428) — на первом запуске готовность никогда бы не подтвердилась.
Оба места чинили одновременно с веб-визардом (POST /api/setup/init)."""

import threading
import time

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


def test_wait_until_ready_raises_immediately_if_server_thread_died(monkeypatch):
    """A dead server thread (e.g. app import blew up) must fail fast
    instead of silently burning the full timeout."""

    def fake_get(url, timeout):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "get", fake_get)
    dead_thread = threading.Thread(target=lambda: None)
    dead_thread.start()
    dead_thread.join()

    start = time.monotonic()
    with pytest.raises(RuntimeError):
        desktop_app._wait_until_ready(
            "http://127.0.0.1:1/api/setup/status", dead_thread, timeout=15.0
        )
    assert time.monotonic() - start < 1.0


def test_kill_stale_browser_processes_targets_known_profile_markers(
    monkeypatch,
):
    """Must pkill by our own profile/driver-cache path markers only —
    never a bare 'chrome', which would also kill the user's regular
    browser session."""
    calls = []
    monkeypatch.setattr(
        desktop_app.subprocess,
        "run",
        lambda cmd, check=False: calls.append(cmd),
    )
    desktop_app._kill_stale_browser_processes()
    patterns = [cmd[-1] for cmd in calls]
    assert patterns == [".chrome_profile_", ".linkedin_profile"]
    assert all(cmd[:2] == ["pkill", "-f"] for cmd in calls)


def test_main_probes_setup_status_not_status(monkeypatch):
    """main() must never poll /api/status directly — it 428s until
    data_folder is set up, so readiness would never be confirmed."""
    probed_urls = []

    monkeypatch.setattr(
        desktop_app, "_kill_stale_browser_processes", lambda: None
    )
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

    def fake_wait_until_ready(url, server_thread=None, timeout=15.0):
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
