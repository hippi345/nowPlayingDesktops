"""Real Linux X11 desktop verification (Xvfb + feh) for PR cross-platform checks."""

from __future__ import annotations

import os
import re
import shutil
import signal
import site
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from now_playing_desktops import cli
from now_playing_desktops.platforms import autostart
from now_playing_desktops.platforms.base import ScreenInfo
from now_playing_desktops.platforms.linux import LinuxWallpaperPlatform
from now_playing_desktops.platforms.linux_backends import FehWallpaperBackend
from now_playing_desktops.platforms.linux_de import LinuxDesktopEnvironment
from now_playing_desktops.runner import NowPlayingRunner, RunnerDeps
from now_playing_desktops.spotify_art import TrackPlayback
from tests.helpers import make_test_cover
from tests.verification_helpers import (
    VERIFY_TRACK,
    assert_centered_within,
    autostart_supports_env_file,
    capture_root_window,
    save_artifact,
    sha256_file,
)

RESOLUTIONS = (
    (1920, 1080, "linux-1080p-desktop.png"),
    (2560, 1440, "linux-1440p-desktop.png"),
    (3840, 2160, "linux-4k-desktop.png"),
)


def _linux_tools_available() -> bool:
    return all(shutil.which(name) for name in ("Xvfb", "feh", "xwd", "convert"))


_display_serial = 300


def _allocate_display() -> str:
    global _display_serial
    _display_serial += 1
    return f":{_display_serial}"


def _start_xvfb(display: str, width: int, height: int) -> subprocess.Popen[bytes]:
    proc = subprocess.Popen(
        ["Xvfb", display, "-screen", "0", f"{width}x{height}x24", "-ac"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(0.4)
    if proc.poll() is not None:
        raise RuntimeError(f"Xvfb failed for {display}")
    return proc


def _pythonpath_for_subprocess() -> str:
    roots = [
        str(Path(__file__).resolve().parents[1] / "src"),
        str(Path.cwd()),
    ]
    roots.extend(site.getsitepackages())
    user_site = site.getusersitepackages()
    if user_site:
        roots.append(user_site)
    return os.pathsep.join(roots)


def _write_dummy_env(path: Path) -> Path:
    path.write_text(
        textwrap.dedent(
            """
            SPOTIPY_CLIENT_ID=dummy-client-id
            SPOTIPY_CLIENT_SECRET=dummy-client-secret
            SPOTIPY_REDIRECT_URI=http://127.0.0.1:8799/callback
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    return path.resolve()


def _feh_platform() -> LinuxWallpaperPlatform:
    return LinuxWallpaperPlatform(
        de=LinuxDesktopEnvironment.OTHER,
        backend=FehWallpaperBackend(),
    )


def _mock_spotify_client():
    return MagicMock(), MagicMock(), lambda: None


def _screen_info(width: int, height: int) -> list[ScreenInfo]:
    return [ScreenInfo(screen_id="0", width=width, height=height, is_primary=True)]


def _make_runner(tmp_path: Path, platform: LinuxWallpaperPlatform) -> NowPlayingRunner:
    cache = tmp_path / "cache"
    state = tmp_path / "state.json"
    return NowPlayingRunner(
        RunnerDeps(
            platform=platform,
            sp=_mock_spotify_client()[0],
            cache_dir=cache,
            state_path=state,
            poll_interval_seconds=0.05,
            on_token_refresh=lambda: None,
            sleep=lambda _s: None,
        )
    )


@pytest.mark.integration
@pytest.mark.parametrize("width,height,artifact_name", RESOLUTIONS)
def test_linux_desktop_resolution_verification(
    tmp_path: Path,
    width: int,
    height: int,
    artifact_name: str,
    monkeypatch,
):
    if not _linux_tools_available():
        pytest.skip("Linux desktop verification tools missing")

    work = tmp_path / f"work-{width}x{height}"
    work.mkdir()
    monkeypatch.setenv("HOME", str(work / "home"))
    Path(work / "home").mkdir(parents=True, exist_ok=True)

    display = _allocate_display()
    monkeypatch.setenv("DISPLAY", display)
    xvfb = _start_xvfb(display, width, height)
    env = {"DISPLAY": display, "HOME": str(work / "home")}
    original = tmp_path / "original.png"
    make_test_cover(256).save(original, format="PNG")
    original_hash = sha256_file(original)
    subprocess.run(["feh", "--bg-fill", str(original)], check=True, env=env, timeout=30)

    platform = _feh_platform()
    runner = _make_runner(work, platform)
    paused = TrackPlayback(
        VERIFY_TRACK.track_id,
        VERIFY_TRACK.art_url,
        VERIFY_TRACK.title,
        VERIFY_TRACK.artist,
        is_playing=False,
    )

    with (
        patch(
            "now_playing_desktops.platforms.linux_screen.list_linux_screens",
            return_value=_screen_info(width, height),
        ),
        patch(
            "now_playing_desktops.runner.fetch_playback_with_backoff",
            side_effect=[VERIFY_TRACK, paused, VERIFY_TRACK],
        ),
        patch(
            "now_playing_desktops.runner.download_album_art",
            side_effect=lambda _u, dest, session=None: make_test_cover().save(dest, "JPEG"),
        ),
    ):
        runner.startup()
        runner.apply_playback_once()
        applied = platform.get_current_wallpaper()
        assert applied is not None
        with Image.open(applied) as composed:
            assert composed.size == (width, height)
            dx, dy = assert_centered_within(composed, width, height)
        assert dx <= 2 and dy <= 2

        screenshot = work / "desktop.png"
        capture_root_window(display, screenshot)
        with Image.open(screenshot) as shot:
            assert shot.size == (width, height)
        save_artifact(Image.open(screenshot), artifact_name)

        runner.apply_playback_once()
        restored = platform.get_current_wallpaper()
        assert restored is not None
        assert sha256_file(restored) == original_hash

        runner.apply_playback_once()
        runner._register_shutdown_handlers()
        handler = signal.getsignal(signal.SIGINT)
        assert handler is not None
        with pytest.raises(KeyboardInterrupt):
            handler(signal.SIGINT, None)
        after_sigint = platform.get_current_wallpaper()
        assert after_sigint is not None
        assert sha256_file(after_sigint) == original_hash

    xvfb.terminate()
    xvfb.wait(timeout=10)


@pytest.mark.integration
def test_linux_restored_wallpaper_artifact(tmp_path: Path, monkeypatch):
    if not _linux_tools_available():
        pytest.skip("Linux desktop verification tools missing")
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    display = _allocate_display()
    xvfb = _start_xvfb(display, 1920, 1080)
    original = tmp_path / "original.png"
    make_test_cover(128).save(original, format="PNG")
    subprocess.run(
        ["feh", "--bg-fill", str(original)],
        check=True,
        env={"DISPLAY": display, "HOME": str(home)},
        timeout=30,
    )
    save_artifact(Image.open(original), "linux-restored.png")
    xvfb.terminate()
    xvfb.wait(timeout=10)


@pytest.mark.integration
def test_linux_cli_run_once(tmp_path: Path, monkeypatch):
    if not _linux_tools_available():
        pytest.skip("Linux desktop verification tools missing")
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    display = _allocate_display()
    xvfb = _start_xvfb(display, 1920, 1080)
    env_file = _write_dummy_env(tmp_path / ".env")
    for key in ("SPOTIPY_CLIENT_ID", "SPOTIPY_CLIENT_SECRET"):
        monkeypatch.setenv(key, "dummy")
    work = tmp_path / "cli"
    cache = work / "cache"
    state = work / "state.json"
    platform = _feh_platform()
    run_argv = ["run", "testuser", "--once", "--cache-dir", str(cache)]
    if autostart_supports_env_file():
        run_argv = [
            "run",
            "testuser",
            "--env-file",
            str(env_file),
            "--once",
            "--cache-dir",
            str(cache),
        ]
    with (
        patch("now_playing_desktops.cli.get_platform", return_value=platform),
        patch(
            "now_playing_desktops.cli.create_spotify_client",
            return_value=_mock_spotify_client(),
        ),
        patch(
            "now_playing_desktops.runner.fetch_playback_with_backoff",
            return_value=VERIFY_TRACK,
        ),
        patch(
            "now_playing_desktops.runner.download_album_art",
            side_effect=lambda _u, dest, session=None: make_test_cover().save(dest, "JPEG"),
        ),
        patch("now_playing_desktops.config.default_cache_dir", return_value=cache),
        patch("now_playing_desktops.config.state_file_path", return_value=state),
        patch(
            "now_playing_desktops.platforms.linux_screen.list_linux_screens",
            return_value=_screen_info(1920, 1080),
        ),
    ):
        os.environ["DISPLAY"] = display
        assert cli.main(run_argv) == 0
    xvfb.terminate()
    xvfb.wait(timeout=10)


@pytest.mark.integration
def test_linux_autostart_enable_disable(tmp_path: Path, monkeypatch):
    if not _linux_tools_available():
        pytest.skip("Linux desktop verification tools missing")
    display = _allocate_display()
    xvfb = _start_xvfb(display, 1920, 1080)
    home = tmp_path / "home"
    home.mkdir()
    config_home = home / ".config"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    monkeypatch.setenv("DISPLAY", display)
    monkeypatch.setattr(autostart.sys, "platform", "linux")

    if autostart_supports_env_file():
        env_file = _write_dummy_env(tmp_path / "oauth.env")
        monkeypatch.setattr(
            autostart,
            "user_config_dir",
            lambda: config_home / "now-playing-desktops",
        )
        mock_entry = Path(__file__).resolve().parent / "mock_cli_entry.py"
        monkeypatch.setattr(
            autostart,
            "_runner_invocation",
            lambda: [sys.executable, str(mock_entry)],
        )
        autostart.enable_autostart(env_file=env_file, username="testuser")
        desktop = config_home / "autostart" / "now-playing-desktops.desktop"
        text = desktop.read_text(encoding="utf-8")
        assert str(env_file) in text
        assert "testuser" in text
        exec_match = re.search(r"^Exec=(.+)$", text, re.MULTILINE)
        assert exec_match
        subprocess.run(
            [
                "env",
                "-i",
                f"HOME={home}",
                f"DISPLAY={display}",
                f"PATH={os.environ.get('PATH', '')}",
                f"PYTHONPATH={_pythonpath_for_subprocess()}",
                "sh",
                "-c",
                exec_match.group(1),
            ],
            check=True,
            timeout=60,
        )
    else:

        def fake_which(name: str) -> str | None:
            if name == "now-playing":
                return f"{sys.executable} -m now_playing_desktops"
            return None

        monkeypatch.setattr("shutil.which", fake_which)
        autostart.enable_autostart()
        desktop = config_home / "autostart" / "now-playing-desktops.desktop"
        text = desktop.read_text(encoding="utf-8")
        assert "run" in text

    autostart.disable_autostart()
    assert not desktop.exists()
    xvfb.terminate()
    xvfb.wait(timeout=10)
