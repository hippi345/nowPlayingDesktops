from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from now_playing_desktops.platforms.linux import LinuxWallpaperPlatform
from now_playing_desktops.platforms.linux_backends import (
    FehWallpaperBackend,
    GnomeWallpaperBackend,
    KdeWallpaperBackend,
    NitrogenWallpaperBackend,
    select_wm_fallback_backend,
)
from now_playing_desktops.platforms.linux_de import LinuxDesktopEnvironment
from tests.helpers import make_test_cover


def test_gnome_set_wallpaper_sets_both_uri_keys(tmp_path: Path):
    image = tmp_path / "bg.png"
    image.write_bytes(b"x")
    backend = GnomeWallpaperBackend()
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with patch("now_playing_desktops.platforms.linux_backends._run", side_effect=fake_run):
        backend.set_wallpaper(image)

    set_cmds = [c for c in calls if c[:3] == ["gsettings", "set", "org.gnome.desktop.background"]]
    keys = {c[3] for c in set_cmds}
    assert "picture-uri" in keys
    assert "picture-uri-dark" in keys


def test_gnome_capture_and_restore_roundtrip():
    backend = GnomeWallpaperBackend()
    snapshot = {
        "backend": "gnome",
        "gsettings": {
            "picture-uri": "'file:///old.png'",
            "picture-uri-dark": "'file:///old-dark.png'",
            "picture-options": "'zoom'",
        },
    }
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with patch("now_playing_desktops.platforms.linux_backends._run", side_effect=fake_run):
        backend.apply_snapshot(snapshot)

    assert any(c[3] == "picture-uri" for c in calls if c[0] == "gsettings")
    assert any(c[3] == "picture-uri-dark" for c in calls if c[0] == "gsettings")


def test_kde_primary_uses_plasma_apply_wallpaperimage(tmp_path: Path):
    image = tmp_path / "bg.jpg"
    image.write_bytes(b"x")
    backend = KdeWallpaperBackend()

    with (
        patch(
            "now_playing_desktops.platforms.linux_backends._which",
            side_effect=lambda name: (
                "/usr/bin/plasma-apply-wallpaperimage"
                if name == "plasma-apply-wallpaperimage"
                else None
            ),
        ),
        patch("now_playing_desktops.platforms.linux_backends._run") as run_mock,
    ):
        backend.set_wallpaper(image)
    run_mock.assert_called_once()
    assert run_mock.call_args[0][0][0] == "plasma-apply-wallpaperimage"


def test_kde_qdbus_fallback_when_no_plasma_apply(tmp_path: Path):
    image = tmp_path / "bg.jpg"
    image.write_bytes(b"x")
    backend = KdeWallpaperBackend()

    def which(name: str):
        if name == "qdbus6":
            return "/usr/bin/qdbus6"
        return None

    with (
        patch("now_playing_desktops.platforms.linux_backends._which", side_effect=which),
        patch("now_playing_desktops.platforms.linux_backends._run") as run_mock,
    ):
        backend.set_wallpaper(image)
    assert run_mock.call_args[0][0][0] == "qdbus6"


def test_wm_fallback_prefers_swaybg_over_feh():
    from now_playing_desktops.platforms.linux_backends import SwaybgWallpaperBackend

    with patch(
        "now_playing_desktops.platforms.linux_backends._which",
        side_effect=lambda name: f"/usr/bin/{name}",
    ):
        assert isinstance(select_wm_fallback_backend(), SwaybgWallpaperBackend)


def test_wm_fallback_selects_feh_when_no_swaybg():
    with patch(
        "now_playing_desktops.platforms.linux_backends._which",
        side_effect=lambda name: "/usr/bin/feh" if name == "feh" else None,
    ):
        assert isinstance(select_wm_fallback_backend(), FehWallpaperBackend)


def test_wm_fallback_selects_nitrogen_when_only_nitrogen():
    with patch(
        "now_playing_desktops.platforms.linux_backends._which",
        side_effect=lambda name: "/usr/bin/nitrogen" if name == "nitrogen" else None,
    ):
        assert isinstance(select_wm_fallback_backend(), NitrogenWallpaperBackend)


def test_feh_get_current_wallpaper_parses_single_quoted_paths(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr("pathlib.Path.home", lambda: home)
    image = tmp_path / "wall.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    fehbg = home / ".fehbg"
    fehbg.write_text(f"feh --no-fehbg --bg-fill '{image}'\n", encoding="utf-8")
    backend = FehWallpaperBackend()
    assert backend.get_current_wallpaper() == image


def test_feh_restore_runs_fehbg_script(tmp_path: Path):
    backend = FehWallpaperBackend()
    snapshot = {"backend": "feh", "fehbg": "feh --bg-fill /wall.jpg"}
    proc = MagicMock()
    with patch(
        "now_playing_desktops.platforms.linux_backends.subprocess.Popen",
        return_value=proc,
    ) as popen:
        backend.apply_snapshot(snapshot)
    popen.assert_called_once()
    proc.wait.assert_called_once()


def test_nitrogen_set_uses_zoom_fill(tmp_path: Path):
    image = tmp_path / "bg.png"
    image.write_bytes(b"x")
    backend = NitrogenWallpaperBackend()
    with patch("now_playing_desktops.platforms.linux_backends._run") as run_mock:
        backend.set_wallpaper(image)
    assert run_mock.call_args[0][0][:2] == ["nitrogen", "--set-zoom-fill"]


def test_linux_platform_capture_restore_snapshot_gnome():
    backend = GnomeWallpaperBackend()
    platform = LinuxWallpaperPlatform(de=LinuxDesktopEnvironment.GNOME, backend=backend)
    snap_return = {"backend": "gnome", "gsettings": {}}
    with patch.object(backend, "capture_snapshot", return_value=snap_return):
        snap = platform.capture_restore_snapshot()
    assert snap["de"] == "gnome"


def test_linux_screen_size_fallback():
    from now_playing_desktops.platforms.linux_screen import list_linux_screens

    with (
        patch(
            "now_playing_desktops.platforms.linux_screen.screens_from_xrandr",
            return_value=[],
        ),
        patch(
            "now_playing_desktops.platforms.linux_screen.screens_from_gnome",
            return_value=[],
        ),
        patch(
            "now_playing_desktops.platforms.linux_screen.screens_from_wlr_randr",
            return_value=[],
        ),
    ):
        screens = list_linux_screens()
    assert screens[0].width == 1920


@pytest.mark.integration
def test_gnome_gsettings_integration_under_dbus(tmp_path: Path):
    if not shutil.which("gsettings") or not shutil.which("dbus-run-session"):
        pytest.skip("gsettings or dbus-run-session missing")
    image = tmp_path / "wall.png"
    make_test_cover(64).save(image, format="PNG")
    uri = f"file://{image.resolve()}"
    backend = GnomeWallpaperBackend()

    def run_in_session(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["dbus-run-session", "--", *cmd],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )

    for key in ("picture-uri", "picture-uri-dark"):
        run_in_session(
            [
                "gsettings",
                "set",
                "org.gnome.desktop.background",
                key,
                f"'{uri}'",
            ]
        )
    get = run_in_session(
        ["gsettings", "get", "org.gnome.desktop.background", "picture-uri"],
    )
    assert uri in get.stdout
    snap = backend.capture_snapshot()
    assert "picture-uri" in snap.get("gsettings", {})


@pytest.mark.integration
def test_feh_integration_under_xvfb(tmp_path: Path):
    if not shutil.which("feh") or not shutil.which("xvfb-run"):
        pytest.skip("feh or xvfb-run missing")
    image = tmp_path / "bg.png"
    make_test_cover(64).save(image, format="PNG")
    backend = FehWallpaperBackend()
    subprocess.run(
        ["xvfb-run", "-a", "feh", "--bg-fill", str(image)],
        check=True,
        timeout=60,
    )
    fehbg = Path.home() / ".fehbg"
    assert fehbg.is_file()
    snap = backend.capture_snapshot()
    assert snap.get("fehbg")
