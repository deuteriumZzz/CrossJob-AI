"""Автозапуск desktop_app.py при входе в систему — macOS (LaunchAgent)
и Windows (реестр HKCU\\...\\Run) в одном месте, вместо разовой ручной
установки plist через терминал."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_LABEL = "com.crossjob-ai.desktop"


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _launch_command() -> list[str]:
    """В PyInstaller-сборке sys.executable — это сам собранный
    .app/.exe, доп. аргумент не нужен. Из исходников — venv-питон +
    путь к desktop_app.py (main._project_root(), тот же приём, что и
    остальной проект использует для PyInstaller-совместимых путей)."""
    if _is_frozen():
        return [sys.executable]
    from main import _project_root

    return [sys.executable, str(_project_root() / "desktop_app.py")]


def is_supported() -> bool:
    return sys.platform in ("darwin", "win32")


# --- macOS: LaunchAgent --------------------------------------------------


def _macos_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{_LABEL}.plist"


def _macos_plist_contents() -> str:
    args_xml = "\n".join(
        f"        <string>{c}</string>" for c in _launch_command()
    )
    log_path = Path.home() / "Library" / "Logs" / f"{_LABEL}.log"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
{args_xml}
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    <key>ThrottleInterval</key>
    <integer>10</integer>
    <key>StandardOutPath</key>
    <string>{log_path}</string>
    <key>StandardErrorPath</key>
    <string>{log_path}</string>
</dict>
</plist>
"""


def _macos_uid() -> str:
    return subprocess.run(
        ["id", "-u"], capture_output=True, text=True, check=True
    ).stdout.strip()


def _macos_is_enabled() -> bool:
    return _macos_plist_path().exists()


def _macos_enable() -> None:
    plist_path = _macos_plist_path()
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_text(_macos_plist_contents(), encoding="utf-8")
    uid = _macos_uid()
    # bootout best-effort — если ещё не загружен, просто вернёт ошибку,
    # игнорируем; нужен перед bootstrap, если plist уже был загружен со
    # старым содержимым (bootstrap поверх уже загруженного label падает).
    subprocess.run(
        ["launchctl", "bootout", f"gui/{uid}/{_LABEL}"], capture_output=True
    )
    subprocess.run(
        ["launchctl", "bootstrap", f"gui/{uid}", str(plist_path)],
        capture_output=True,
        check=True,
    )


def _macos_disable() -> None:
    uid = _macos_uid()
    subprocess.run(
        ["launchctl", "bootout", f"gui/{uid}/{_LABEL}"], capture_output=True
    )
    _macos_plist_path().unlink(missing_ok=True)


# --- Windows: HKCU Run key ------------------------------------------------

_WINDOWS_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _windows_is_enabled() -> bool:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _WINDOWS_RUN_KEY) as key:
            winreg.QueryValueEx(key, _LABEL)
            return True
    except FileNotFoundError:
        return False


def _windows_enable() -> None:
    import winreg

    value = " ".join(f'"{c}"' for c in _launch_command())
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _WINDOWS_RUN_KEY) as key:
        winreg.SetValueEx(key, _LABEL, 0, winreg.REG_SZ, value)


def _windows_disable() -> None:
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _WINDOWS_RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, _LABEL)
    except FileNotFoundError:
        pass


# --- Public API ------------------------------------------------------------


def is_enabled() -> bool:
    if sys.platform == "darwin":
        return _macos_is_enabled()
    if sys.platform == "win32":
        return _windows_is_enabled()
    return False


def set_enabled(enabled: bool) -> None:
    if sys.platform == "darwin":
        _macos_enable() if enabled else _macos_disable()
    elif sys.platform == "win32":
        _windows_enable() if enabled else _windows_disable()
    else:
        raise RuntimeError(f"Автозапуск не поддерживается на {sys.platform}.")
