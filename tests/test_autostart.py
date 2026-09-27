from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from now_playing_desktops.platforms import autostart


def _env_file(tmp_path: Path) -> Path:
    path = tmp_path / "oauth.env"
    path.write_text(
        "SPOTIPY_CLIENT_ID=id\nSPOTIPY_CLIENT_SECRET=secret\n",
        encoding="utf-8",
    )
    return path.resolve()


def test_linux_autostart_enable_disable(tmp_path: Path, monkeypatch):
    config_home = tmp_path / "xdg-config"
    env_file = _env_file(tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    monkeypatch.setattr(autostart.sys, "platform", "linux")
    assert autostart.autostart_enabled() is False
    autostart.enable_autostart(env_file=env_file, username="user")
    desktop = config_home / "autostart" / "now-playing-desktops.desktop"
    assert desktop.is_file()
    assert autostart.autostart_enabled() is True
    autostart.disable_autostart()
    assert autostart.autostart_enabled() is False


def test_windows_autostart_enable_disable(tmp_path: Path):
    env_file = _env_file(tmp_path)
    with (
        patch.object(autostart.sys, "platform", "win32"),
        patch("now_playing_desktops.env_loader.load_environment"),
        patch(
            "now_playing_desktops.env_loader.find_env_file",
            return_value=env_file,
        ),
        patch(
            "now_playing_desktops.env_loader.spotify_credentials_configured",
            return_value=True,
        ),
        patch("now_playing_desktops.platforms.autostart._windows_enable_autostart") as enable,
        patch("now_playing_desktops.platforms.autostart._windows_disable_autostart") as disable,
        patch(
            "now_playing_desktops.platforms.autostart._windows_autostart_enabled",
            return_value=True,
        ),
    ):
        autostart.enable_autostart(env_file=env_file, username="u")
        enable.assert_called_once()
        assert autostart.autostart_enabled() is True
        autostart.disable_autostart()
        disable.assert_called_once()


def test_macos_autostart_enable_disable(tmp_path: Path, monkeypatch):
    env_file = _env_file(tmp_path)
    monkeypatch.setattr(autostart.sys, "platform", "darwin")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    autostart.enable_autostart(env_file=env_file, username="user")
    assert autostart._macos_plist_path().is_file()
    autostart.disable_autostart()
    assert not autostart._macos_plist_path().exists()
