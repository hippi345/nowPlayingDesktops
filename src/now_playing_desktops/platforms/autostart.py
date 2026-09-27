"""Login autostart registration per OS."""

from __future__ import annotations

import os
import plistlib
import sys
from pathlib import Path


def _windows_run_key_name() -> str:
    return "now-playing-desktops"


def _windows_run_command() -> str:
    import shutil

    exe = shutil.which("now-playing")
    if exe:
        return f'"{exe}" run %USERNAME%'
    return f'"{sys.executable}" -m now_playing_desktops run %USERNAME%'


def autostart_enabled() -> bool:
    if sys.platform == "win32":
        return _windows_autostart_enabled()
    if sys.platform == "darwin":
        return _macos_autostart_enabled()
    if sys.platform == "linux":
        return _linux_autostart_enabled()
    return False


def enable_autostart() -> None:
    if sys.platform == "win32":
        _windows_enable_autostart()
    elif sys.platform == "darwin":
        _macos_enable_autostart()
    elif sys.platform == "linux":
        _linux_enable_autostart()
    else:
        raise OSError(f"Autostart not supported on {sys.platform}")


def disable_autostart() -> None:
    if sys.platform == "win32":
        _windows_disable_autostart()
    elif sys.platform == "darwin":
        _macos_disable_autostart()
    elif sys.platform == "linux":
        _linux_disable_autostart()
    else:
        raise OSError(f"Autostart not supported on {sys.platform}")


def _windows_autostart_enabled() -> bool:
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
        ) as key:
            winreg.QueryValueEx(key, _windows_run_key_name())
            return True
    except OSError:
        return False


def _windows_enable_autostart() -> None:
    import winreg

    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        winreg.SetValueEx(key, _windows_run_key_name(), 0, winreg.REG_SZ, _windows_run_command())


def _windows_disable_autostart() -> None:
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.DeleteValue(key, _windows_run_key_name())
    except OSError:
        pass


def _linux_config_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME", "").strip()
    if xdg:
        return Path(xdg)
    return Path.home() / ".config"


def _linux_desktop_path() -> Path:
    return _linux_config_dir() / "autostart" / "now-playing-desktops.desktop"


def _linux_autostart_enabled() -> bool:
    return _linux_desktop_path().is_file()


def _linux_enable_autostart() -> None:
    import shutil

    exe = shutil.which("now-playing") or f"{sys.executable} -m now_playing_desktops"
    path = _linux_desktop_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Now Playing Desktops\n"
        f"Exec={exe} run %u\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n"
    )
    path.write_text(content, encoding="utf-8")


def _linux_disable_autostart() -> None:
    path = _linux_desktop_path()
    if path.is_file():
        path.unlink()


def _macos_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / "com.nowplayingdesktops.agent.plist"


def _macos_autostart_enabled() -> bool:
    return _macos_plist_path().is_file()


def _macos_enable_autostart() -> None:
    import shutil

    exe = shutil.which("now-playing-macos") or shutil.which("now-playing")
    if not exe:
        exe = f"{sys.executable} -m now_playing_desktops"
    plist_path = _macos_plist_path()
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "Label": "com.nowplayingdesktops.agent",
        "ProgramArguments": [exe, "run", "SPOTIFY_USERNAME"],
        "RunAtLoad": True,
        "KeepAlive": False,
    }
    with plist_path.open("wb") as handle:
        plistlib.dump(payload, handle)


def _macos_disable_autostart() -> None:
    path = _macos_plist_path()
    if path.is_file():
        path.unlink()
