"""Десктопная обёртка вокруг src/webui/api.py — тот же локальный
веб-дашборд, что доступен через `uvicorn src.webui.api:app`, но в
нативном окне (pywebview) без вкладок браузера. Требует
requirements-desktop.txt (fastapi/uvicorn/pywebview), которые не
нужны для обычного CLI/cron-использования main.py."""

from __future__ import annotations

import socket
import threading
import time

import httpx
import uvicorn
import webview


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_until_ready(
    url: str, server_thread: threading.Thread | None = None, timeout: float = 15.0
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        # Если поток сервера уже умер (например, ошибка импорта
        # приложения), нет смысла молча ждать оставшийся таймаут —
        # это только прячет настоящую причину за бесполезным
        # "did not become ready".
        if server_thread is not None and not server_thread.is_alive():
            raise RuntimeError(
                "Server thread exited before becoming ready — see traceback above."
            )
        try:
            httpx.get(url, timeout=1).raise_for_status()
            return
        except httpx.HTTPError:
            time.sleep(0.2)
    raise RuntimeError(f"Server at {url} did not become ready in time.")


def main() -> None:
    # Нет проверки data_folder здесь — если его ещё нет, дашборд сам
    # покажет экран первого запуска (GET /api/setup/status), как и в
    # обычном браузере. Раньше это место жёстко завершало процесс
    # ДО того, как окно вообще открывалось — для упакованного .app
    # без видимого терминала пользователь просто не понимал, почему
    # приложение мгновенно закрывается.
    port = _free_port()
    server_config = uvicorn.Config(
        "src.webui.api:app", host="127.0.0.1", port=port, log_level="warning"
    )
    server = uvicorn.Server(server_config)
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    url = f"http://127.0.0.1:{port}/"
    # /api/setup/status, не /api/status — последний требует
    # настроенный data_folder (иначе 428), а на первом запуске его
    # ещё нет, и проверка готовности никогда бы не прошла.
    _wait_until_ready(f"{url}api/setup/status", server_thread)

    # Автостарт демона при каждом запуске приложения — раньше нужно
    # было руками жать "Запустить" после каждого перезапуска процесса
    # (состояние демона живёт только в памяти AppContext), из-за чего
    # LaunchAgent-автозапуск (см. scripts/install_launch_agent.sh) сам
    # по себе ничего не планировал бы. Best-effort: если data_folder
    # ещё не настроен (первый запуск), /api/daemon/start вернёт 428 —
    # не мешает открытию окна, дашборд покажет мастер настройки как
    # обычно.
    try:
        httpx.post(f"{url}api/daemon/start", timeout=5).raise_for_status()
    except httpx.HTTPError:
        pass

    webview.create_window(
        "CrossJob-AI", url, width=1200, height=800, min_size=(900, 600)
    )
    webview.start()

    server.should_exit = True
    server_thread.join(timeout=5)


if __name__ == "__main__":
    main()
