from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from now_playing_desktops.platforms.base import ScreenInfo
from now_playing_desktops.platforms.linux import LinuxWallpaperPlatform
from now_playing_desktops.platforms.linux_backends import (
    FehWallpaperBackend,
    XfceWallpaperBackend,
)
from now_playing_desktops.platforms.linux_de import LinuxDesktopEnvironment


def _sample_keys() -> list[str]:
    return [
        "/backdrop/screen0/monitorHDMI-1/workspace0/last-image",
        "/backdrop/screen0/monitor0/workspace1/last-image",
    ]


def test_xfce_backend_selects_when_xfconf_available():
    with patch.object(XfceWallpaperBackend, "available", return_value=True):
        platform = LinuxWallpaperPlatform(de=LinuxDesktopEnvironment.XFCE)
    assert isinstance(platform._backend, XfceWallpaperBackend)


def test_xfce_platform_falls_back_without_xfconf():
    with (
        patch.object(XfceWallpaperBackend, "available", return_value=False),
        patch(
            "now_playing_desktops.platforms.linux.select_wm_fallback_backend",
            return_value=FehWallpaperBackend(),
        ),
    ):
        platform = LinuxWallpaperPlatform(de=LinuxDesktopEnvironment.XFCE)
    assert isinstance(platform._backend, FehWallpaperBackend)


def test_xfce_set_wallpaper_updates_all_last_image_keys(tmp_path: Path):
    image = tmp_path / "wall.png"
    image.write_bytes(b"\x89PNG")
    backend = XfceWallpaperBackend()
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with (
        patch("now_playing_desktops.platforms.linux_backends._run", side_effect=fake_run),
        patch.object(
            backend,
            "_xfconf_list_properties",
            return_value=_sample_keys(),
        ),
        patch.object(backend, "_xfconf_get", return_value="5"),
    ):
        backend.set_wallpaper(image)

    set_cmds = [
        c
        for c in calls
        if len(c) >= 7 and c[0] == "xfconf-query" and c[-2] == "-s" and "last-image" in c[4]
    ]
    assert len(set_cmds) == 2
    assert all(c[-1] == str(image.resolve()) for c in set_cmds)


def test_xfce_refresh_uses_alternating_paths_for_same_source(tmp_path: Path):
    image = tmp_path / "wall.png"
    image.write_bytes(b"\x89PNG")
    backend = XfceWallpaperBackend()
    paths_used: list[str] = []

    def fake_run(cmd, **kwargs):
        if cmd[-2:] == ["-s", cmd[-1]] and len(cmd) >= 5 and "last-image" in cmd[4]:
            paths_used.append(cmd[-1])
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with (
        patch("now_playing_desktops.platforms.linux_backends._run", side_effect=fake_run),
        patch.object(backend, "_xfconf_list_properties", return_value=_sample_keys()[:1]),
        patch.object(backend, "_xfconf_get", return_value="5"),
    ):
        backend.set_wallpaper(image)
        backend.set_wallpaper(image)

    assert len(paths_used) == 2
    assert paths_used[0] == str(image.resolve())
    assert paths_used[1] != paths_used[0]
    assert paths_used[1].endswith(".npd-xfce-1.png")


def test_xfce_capture_and_restore_roundtrip():
    backend = XfceWallpaperBackend()
    snapshot = {
        "backend": "xfce",
        "xfconf_last_image": {
            _sample_keys()[0]: "/home/user/old.jpg",
        },
        "xfconf_image_style": {
            f"{_sample_keys()[0].rsplit('/', 1)[0]}/image-style": "3",
        },
    }
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with patch("now_playing_desktops.platforms.linux_backends._run", side_effect=fake_run):
        backend.apply_snapshot(snapshot)

    set_image = [
        c for c in calls if c[0] == "xfconf-query" and c[-2] == "-s" and "last-image" in c[4]
    ]
    set_style = [
        c for c in calls if c[0] == "xfconf-query" and c[-2] == "-s" and "image-style" in c[4]
    ]
    assert set_image and set_image[0][-1] == "/home/user/old.jpg"
    assert set_style and set_style[0][-1] == "3"


def test_xfce_restore_resets_missing_image_style():
    backend = XfceWallpaperBackend()
    style_key = f"{_sample_keys()[0].rsplit('/', 1)[0]}/image-style"
    snapshot = {
        "backend": "xfce",
        "xfconf_last_image": {_sample_keys()[0]: "/wall.jpg"},
        "xfconf_image_style": {style_key: ""},
    }
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with patch("now_playing_desktops.platforms.linux_backends._run", side_effect=fake_run):
        backend.apply_snapshot(snapshot)

    assert any(c[0] == "xfconf-query" and "-r" in c and style_key in c for c in calls)


def test_xfce_falls_back_to_feh_when_no_keys(tmp_path: Path):
    image = tmp_path / "wall.png"
    image.write_bytes(b"x")
    feh = FehWallpaperBackend()
    backend = XfceWallpaperBackend(feh_fallback=feh)

    with (
        patch.object(backend, "_ensure_last_image_keys", return_value=None),
        patch.object(feh, "set_wallpaper") as feh_set,
    ):
        backend.set_wallpaper(image)

    feh_set.assert_called_once_with(image)
    assert backend._delegated_to_feh


def test_xfce_capture_lists_only_last_image_pattern():
    backend = XfceWallpaperBackend()

    def list_props():
        return _sample_keys() + ["/backdrop/screen0/monitor0/workspace0/image-show"]

    def fake_get(prop: str) -> str | None:
        if prop.endswith("last-image"):
            return f"/tmp/{prop.split('/')[-2]}.jpg"
        if prop.endswith("image-style"):
            return "4"
        return None

    with (
        patch.object(backend, "_xfconf_list_properties", side_effect=list_props),
        patch.object(backend, "_xfconf_get", side_effect=fake_get),
    ):
        snap = backend.capture_snapshot()

    assert snap["backend"] == "xfce"
    assert len(snap["xfconf_last_image"]) == 2
    assert len(snap["xfconf_image_style"]) == 2


def test_linux_platform_restore_uses_xfce_backend():
    platform = LinuxWallpaperPlatform(
        de=LinuxDesktopEnvironment.XFCE,
        backend=XfceWallpaperBackend(),
    )
    snapshot = {
        "backend": "xfce",
        "xfconf_last_image": {},
        "xfconf_image_style": {},
    }
    with patch.object(XfceWallpaperBackend, "apply_snapshot") as apply_mock:
        platform.apply_restore_snapshot(snapshot)
    apply_mock.assert_called_once_with(snapshot)
    assert isinstance(platform._backend, XfceWallpaperBackend)


def test_xfce_create_monitor_keys_when_list_empty(tmp_path: Path):
    image = tmp_path / "wall.png"
    image.write_bytes(b"x")
    backend = XfceWallpaperBackend()
    created: list[str] = []

    def fake_run(cmd, **kwargs):
        if "-n" in cmd:
            created.append(cmd[4])
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with (
        patch("now_playing_desktops.platforms.linux_backends._run", side_effect=fake_run),
        patch.object(backend, "_xfconf_list_properties", return_value=[]),
        patch(
            "now_playing_desktops.platforms.linux_backends.list_linux_screens",
            return_value=[
                ScreenInfo(screen_id="DP-1", width=1920, height=1080, is_primary=True),
            ],
        ),
        patch.object(backend, "_xfconf_get", return_value=None),
    ):
        backend.set_wallpaper(image)

    assert "/backdrop/screen0/monitorDP-1/workspace0/last-image" in created
