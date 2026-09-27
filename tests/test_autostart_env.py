from __future__ import annotations

import contextlib
import plistlib
import sys
from pathlib import Path

import pytest

from now_playing_desktops import env_loader
from now_playing_desktops.platforms import autostart


def _write_env(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "SPOTIPY_CLIENT_ID=test-id\nSPOTIPY_CLIENT_SECRET=test-secret\n",
        encoding="utf-8",
    )
    return path.resolve()


def test_enable_autostart_refuses_without_env(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(env_loader, "user_config_dir", lambda: tmp_path / "cfg")
    monkeypatch.setattr(autostart.sys, "platform", "linux")
    with pytest.raises(autostart.AutostartSetupError) as exc:
        autostart.enable_autostart()
    assert ".env" in str(exc.value)


def test_windows_enable_writes_env_file_and_literal_username(tmp_path: Path, monkeypatch):
    env_file = _write_env(tmp_path / "oauth.env")
    captured: dict[str, object] = {}

    class FakeWinreg:
        REG_SZ = 1
        HKEY_CURRENT_USER = object()
        KEY_SET_VALUE = 8

        @staticmethod
        def CreateKeyEx(*_args, **_kwargs):
            return _FakeKey()

        @staticmethod
        def SetValueEx(_key, _name, _reserved, reg_type, value):
            captured["reg_type"] = reg_type
            captured["value"] = value

    class _FakeKey:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    monkeypatch.setitem(sys.modules, "winreg", FakeWinreg)
    monkeypatch.setattr(autostart.sys, "platform", "win32")
    monkeypatch.setattr(
        autostart,
        "_runner_invocation",
        lambda: [str(tmp_path / "Python312" / "python.exe")],
    )

    autostart.enable_autostart(env_file=env_file, username="real_user")

    assert captured["reg_type"] == FakeWinreg.REG_SZ
    command = str(captured["value"])
    assert "--env-file" in command
    assert str(env_file) in command
    assert "real_user" in command
    assert "%" not in command


def test_linux_desktop_contains_env_file_and_workdir(tmp_path: Path, monkeypatch):
    env_file = _write_env(tmp_path / "oauth.env")
    config_home = tmp_path / "xdg-config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    monkeypatch.setattr(autostart.sys, "platform", "linux")
    monkeypatch.setattr(autostart, "user_config_dir", lambda: tmp_path / "app-config")
    monkeypatch.setattr(
        autostart,
        "_runner_invocation",
        lambda: ["/usr/bin/now-playing"],
    )

    autostart.enable_autostart(env_file=env_file, username="linux_user")

    desktop = config_home / "autostart" / "now-playing-desktops.desktop"
    text = desktop.read_text(encoding="utf-8")
    assert "--env-file" in text
    assert env_file.name in text
    assert "linux_user" in text
    assert f"Path={tmp_path / 'app-config'}" in text


def test_macos_plist_contains_env_file(tmp_path: Path, monkeypatch):
    env_file = _write_env(tmp_path / "oauth.env")
    monkeypatch.setattr(autostart.sys, "platform", "darwin")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(autostart, "user_config_dir", lambda: tmp_path / "app-config")
    monkeypatch.setattr(
        autostart,
        "_runner_invocation",
        lambda: ["/usr/bin/now-playing"],
    )

    autostart.enable_autostart(env_file=env_file, username="mac_user")

    plist_path = tmp_path / "Library" / "LaunchAgents" / "com.nowplayingdesktops.agent.plist"
    with plist_path.open("rb") as handle:
        payload = plistlib.load(handle)
    assert "--env-file" in payload["ProgramArguments"]
    assert str(env_file) in payload["ProgramArguments"]
    assert payload["ProgramArguments"][-1] == "mac_user"
    assert payload["WorkingDirectory"] == str(tmp_path / "app-config")


def test_build_run_argv_omits_username_when_none(tmp_path: Path):
    env_file = tmp_path / ".env"
    argv = autostart.build_run_argv(env_file=env_file, username=None)
    assert argv[-2:] == ["--env-file", str(env_file)]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows registry integration test")
def test_windows_run_key_integration(tmp_path: Path, monkeypatch):
    import winreg

    env_file = _write_env(tmp_path / "oauth.env")
    test_name = "now-playing-desktops-ci-test"
    monkeypatch.setattr(autostart, "_windows_run_key_name", lambda: test_name)
    monkeypatch.setattr(
        autostart,
        "_runner_invocation",
        lambda: [sys.executable, "-m", "now_playing_desktops"],
    )

    autostart._windows_enable_autostart(env_file=env_file, username="ci_user", source="auto")
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
        ) as key:
            value, reg_type = winreg.QueryValueEx(key, test_name)
        assert reg_type == winreg.REG_SZ
        assert "--env-file" in value
        assert str(env_file) in value
        assert "ci_user" in value
        assert "%" not in value
    finally:
        with (
            winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE,
            ) as key,
            contextlib.suppress(OSError),
        ):
            winreg.DeleteValue(key, test_name)
