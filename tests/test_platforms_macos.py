from __future__ import annotations

import plistlib
import sys
from pathlib import Path
from unittest.mock import patch

from now_playing_desktops.platforms import autostart
from now_playing_desktops.platforms.base import ScreenInfo
from now_playing_desktops.platforms.macos import MacOSWallpaperPlatform
from now_playing_desktops.wallpaper_snapshot import file_digest


def test_macos_set_all_screens_via_osascript(tmp_path: Path):
    image = tmp_path / "bg.jpg"
    image.write_bytes(b"x")
    platform = MacOSWallpaperPlatform()
    if sys.platform == "darwin":
        with (
            patch("now_playing_desktops.platforms.macos._PYOBJC_AVAILABLE", False),
            patch("now_playing_desktops.platforms.macos.subprocess.run") as run_mock,
        ):
            platform.set_wallpaper(image)
            run_mock.assert_called()
    else:
        with patch("now_playing_desktops.platforms.macos.subprocess.run") as run_mock:
            platform._set_all_screens(image)
            run_mock.assert_called_once()
            assert "every desktop" in run_mock.call_args[0][0][-1]


def test_macos_capture_restore_per_screen(tmp_path: Path):
    a = tmp_path / "a.jpg"
    b = tmp_path / "b.jpg"
    a.write_bytes(b"a")
    b.write_bytes(b"b")
    platform = MacOSWallpaperPlatform()
    screens = [
        ScreenInfo(screen_id="1", width=1920, height=1080, is_primary=True),
        ScreenInfo(screen_id="2", width=1280, height=720, is_primary=False),
    ]
    with (
        patch.object(platform, "list_screens", return_value=screens),
        patch.object(
            platform,
            "get_current_wallpaper",
            side_effect=lambda *, screen_id=None: a if screen_id == "1" else b,
        ),
    ):
        snap = platform.capture_restore_snapshot(state_dir=tmp_path / "state")
    assert snap["screens"]["1"] == str(a)
    assert snap["screens"]["2"] == str(b)

    calls: list[Path] = []

    def record(path: Path, *, screen_id: str | None = None) -> None:
        calls.append(path)

    with patch.object(platform, "set_wallpaper", side_effect=record):
        platform.apply_restore_snapshot(snap)
    assert calls == [a, b]


def test_macos_osascript_escapes_spaces_and_quotes(tmp_path: Path):
    if sys.platform == "win32":
        nested = tmp_path / "my wall folder"
        image = nested / "bg.jpg"
        nested.mkdir()
        image.write_bytes(b"x")
        platform = MacOSWallpaperPlatform()
        with patch("now_playing_desktops.platforms.macos.subprocess.run") as run_mock:
            platform._set_all_screens(image)
        script = run_mock.call_args[0][0][-1]
        assert "every desktop" in script
        assert "my wall folder" in script
        return

    nested = tmp_path / 'my "wall" folder'
    nested.mkdir()
    image = nested / "bg.jpg"
    image.write_bytes(b"x")
    platform = MacOSWallpaperPlatform()
    with patch("now_playing_desktops.platforms.macos.subprocess.run") as run_mock:
        platform._set_all_screens(image)
    script = run_mock.call_args[0][0][-1]
    assert "every desktop" in script
    assert '\\"wall\\"' in script
    assert str(image) in script.replace('\\"', '"')


def test_macos_capture_stable_copy_roundtrip(tmp_path: Path):
    original = tmp_path / "wallpaper.png"
    original.write_bytes(b"\x89PNG\r\n\x1a\nmac-wall")
    platform = MacOSWallpaperPlatform()
    with (
        patch.object(platform, "list_screens", return_value=[]),
        patch.object(platform, "get_current_wallpaper", return_value=original),
    ):
        snap = platform.capture_restore_snapshot(state_dir=tmp_path / "state")
    stable = Path(snap["stable_path"])
    assert stable.is_file()
    assert stable.read_bytes() == original.read_bytes()
    assert snap["content_hash"] == file_digest(original.read_bytes())


def test_macos_launch_agent_plist_shape(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(autostart.sys, "platform", "darwin")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(
        "shutil.which",
        lambda name: "/usr/bin/now-playing-macos" if name == "now-playing-macos" else None,
    )
    from tests.verification_helpers import autostart_supports_env_file

    if autostart_supports_env_file():
        env_file = tmp_path / "oauth.env"
        env_file.write_text(
            "SPOTIPY_CLIENT_ID=test-id\nSPOTIPY_CLIENT_SECRET=test-secret\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(autostart, "user_config_dir", lambda: tmp_path / "app-config")
        monkeypatch.setattr(
            autostart,
            "_runner_invocation",
            lambda: ["/usr/bin/python3", "-m", "now_playing_desktops"],
        )
        autostart.enable_autostart(env_file=env_file.resolve(), username="mac_user")
    else:
        autostart.enable_autostart()

    plist_path = tmp_path / "Library" / "LaunchAgents" / "com.nowplayingdesktops.agent.plist"
    with plist_path.open("rb") as handle:
        payload = plistlib.load(handle)
    assert payload["RunAtLoad"] is True
    args = payload["ProgramArguments"]
    assert args[1] == "run"
    if autostart_supports_env_file():
        assert payload["WorkingDirectory"] == str(tmp_path / "app-config")
        assert "--env-file" in args
        env_index = args.index("--env-file")
        assert Path(args[env_index + 1]).is_absolute()
        assert args[-1] == "mac_user"
    else:
        assert args[0] == "/usr/bin/now-playing-macos"
        assert args[-1] == "SPOTIFY_USERNAME"
