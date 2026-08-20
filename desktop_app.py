"""Десктопная обёртка вокруг src/webui/api.py — тот же локальный
веб-дашборд, что доступен через `uvicorn src.webui.api:app`, но в
нативном окне (pywebview) без вкладок браузера. Требует
requirements-desktop.txt (fastapi/uvicorn/pywebview), которые не
нужны для обычного CLI/cron-использования main.py."""

from __future__ import annotations

import socket
import sys
import threading
import time
from pathlib import Path

import httpx
import uvicorn
import webview

DATA_FOLDER = Path("data_folder")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_until_ready(url: str, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            httpx.get(url, timeout=1).raise_for_status()
            return
        except httpx.HTTPError:
            time.sleep(0.2)
    raise RuntimeError(f"Server at {url} did not become ready in time.")


def main() -> None:
    if not DATA_FOLDER.is_dir():
        print(
            f"Data folder not found: {DATA_FOLDER}. Copy "
            "data_folder_example to data_folder and fill it in first "
            "(see docs/GUIDE.md)."
        )
        sys.exit(1)

    port = _free_port()
    server_config = uvicorn.Config(
        "src.webui.api:app", host="127.0.0.1", port=port, log_level="warning"
    )
    server = uvicorn.Server(server_config)
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    url = f"http://127.0.0.1:{port}/"
    _wait_until_ready(f"{url}api/status")

    webview.create_window(
        "CrossJob-AI", url, width=1200, height=800, min_size=(900, 600)
    )
    webview.start()

    server.should_exit = True
    server_thread.join(timeout=5)


if __name__ == "__main__":
    main()
