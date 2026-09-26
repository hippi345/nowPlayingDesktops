from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

from now_playing_desktops.platforms import autostart


def test_linux_autostart_enable_disable(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert autostart.autostart_enabled() is False
    autostart.enable_autostart()
    desktop = tmp_path / ".config" / "autostart" / "now-playing-desktops.desktop"
    assert desktop.is_file()
    assert autostart.autostart_enabled() is True
    autostart.disable_autostart()
    assert autostart.autostart_enabled() is False


def test_windows_autostart_enable_disable():
    if sys.platform != "win32":
        with (
            patch.object(autostart.sys, "platform", "win32"),
            patch("now_playing_desktops.platforms.autostart._windows_enable_autostart") as enable,
            patch("now_playing_desktops.platforms.autostart._windows_disable_autostart") as disable,
            patch(
                "now_playing_desktops.platforms.autostart._windows_autostart_enabled",
                return_value=True,
            ),
        ):
            autostart.enable_autostart()
            enable.assert_called_once()
            assert autostart.autostart_enabled() is True
            autostart.disable_autostart()
            disable.assert_called_once()
        return
    autostart.disable_autostart()
    autostart.enable_autostart()
    assert autostart.autostart_enabled() is True
    autostart.disable_autostart()
    assert autostart.autostart_enabled() is False


def test_macos_autostart_enable_disable(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(autostart.sys, "platform", "darwin")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    autostart.enable_autostart()
    assert autostart._macos_plist_path().is_file()
    autostart.disable_autostart()
    assert not autostart._macos_plist_path().exists()
