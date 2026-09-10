"""Headless-демон (`main.py --daemon`) как системная фоновая служба —
отдельно от автозапуска GUI (см. autostart.py: тот поднимает
desktop_app.py при входе и не перезапускает после чистого закрытия
окна; этот держит планировщик живым сам по себе, с автоперезапуском
при ЛЮБОМ завершении, включая падение). Раньше ставилось вручную через
launchctl в терминале — теперь то же самое одной кнопкой в настройках.

Только из исходников: собранный .app/.exe бандлит (desktop_app.spec)
только GUI, отдельного headless-бинарника под main.py --daemon пока
нет — is_supported() поэтому явно False во frozen-сборке, а не падает
на несуществующем пути."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_LABEL = "com.crossjob-ai.daemon"
_WINDOWS_TASK_NAME = "CrossJob-AI Daemon"


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def is_supported() -> bool:
    return not _is_frozen() and sys.platform in ("darwin", "win32")


def _project_root() -> Path:
    from main import _project_root as _root

    return _root()


def _python_executable() -> Path:
    venv_python = _project_root() / "venv" / "bin" / "python"
    return venv_python if venv_python.exists() else Path(sys.executable)


# --- macOS: LaunchAgent --------------------------------------------------


def _macos_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{_LABEL}.plist"


def _macos_plist_contents() -> str:
    root = _project_root()
    log_path = Path.home() / "Library" / "Logs" / f"{_LABEL}.log"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{_python_executable()}</string>
        <string>{root / "main.py"}</string>
        <string>--daemon</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{root}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
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
    # bootout best-effort — если уже загружен со старым содержимым,
    # bootstrap поверх него падает (см. autostart.py — тот же приём).
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


# --- Windows: Scheduled Task -----------------------------------------------


def _windows_is_enabled() -> bool:
    result = subprocess.run(
        ["schtasks", "/query", "/tn", _WINDOWS_TASK_NAME],
        capture_output=True,
    )
    return result.returncode == 0


def _windows_enable() -> None:
    """schtasks /create само не умеет "перезапускать при падении" —
    это поле есть только в полном определении задачи. Проще собрать
    через PowerShell (Register-ScheduledTask), чем вручную писать XML
    для schtasks /create /xml."""
    root = _project_root()
    python = _python_executable()
    script = (
        f"$action = New-ScheduledTaskAction -Execute '{python}' "
        f"-Argument '\"{root / 'main.py'}\" --daemon' "
        f"-WorkingDirectory '{root}'; "
        "$trigger = New-ScheduledTaskTrigger -AtLogOn; "
        "$settings = New-ScheduledTaskSettingsSet "
        "-RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) "
        "-ExecutionTimeLimit ([TimeSpan]::Zero) "
        "-AllowStartIfOnBatteries -DontStopIfGoingOnBatteries; "
        f"Register-ScheduledTask -TaskName '{_WINDOWS_TASK_NAME}' "
        "-Action $action -Trigger $trigger -Settings $settings -Force"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", script], check=True
    )
    subprocess.run(
        ["schtasks", "/run", "/tn", _WINDOWS_TASK_NAME], capture_output=True
    )


def _windows_disable() -> None:
    subprocess.run(
        ["schtasks", "/end", "/tn", _WINDOWS_TASK_NAME], capture_output=True
    )
    subprocess.run(
        ["schtasks", "/delete", "/tn", _WINDOWS_TASK_NAME, "/f"],
        capture_output=True,
    )


# --- Public API --------------------------------------------------------


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
        raise RuntimeError(
            f"Фоновый демон не поддерживается на {sys.platform}."
        )
