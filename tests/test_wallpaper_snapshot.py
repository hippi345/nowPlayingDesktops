from __future__ import annotations

from pathlib import Path

import pytest

from now_playing_desktops.wallpaper_snapshot import (
    attach_stable_copy_to_snapshot,
    bytes_match_render,
    collect_render_content_hashes,
    copy_file_to_stable_wallpaper,
    extension_from_magic,
    file_digest,
    should_preserve_existing_snapshot,
)


def test_extension_from_magic_detects_png_and_jpeg():
    assert extension_from_magic(b"\x89PNG\r\n\x1a\n") == ".png"
    assert extension_from_magic(b"\xff\xd8\xff\x00") == ".jpg"


def test_collect_render_content_hashes_includes_composed_files(tmp_path: Path):
    composed = tmp_path / "cache" / "composed"
    composed.mkdir(parents=True)
    render = composed / "track.png"
    render.write_bytes(b"\x89PNG\r\n\x1a\nrender")
    digests = collect_render_content_hashes(tmp_path / "cache")
    assert file_digest(render.read_bytes()) in digests


def test_attach_stable_copy_skips_generated_render_path(tmp_path: Path):
    cache = tmp_path / "cache"
    cache.mkdir()
    ours = cache / "wall.png"
    ours.write_bytes(b"\x89PNG\r\n\x1a\nours")
    snap = attach_stable_copy_to_snapshot(
        {"backend": "test"},
        state_dir=tmp_path / "state",
        source_path=ours,
        source_bytes=None,
        generated_dir=cache,
    )
    assert snap.get("stable_path") is None


def test_attach_stable_copy_skips_bytes_matching_render_digest(tmp_path: Path):
    cache = tmp_path / "cache"
    cache.mkdir()
    data = b"\x89PNG\r\n\x1a\nalbum-art"
    (cache / "composed.png").write_bytes(data)
    external = tmp_path / "outside.png"
    external.write_bytes(data)
    snap = attach_stable_copy_to_snapshot(
        {"backend": "test"},
        state_dir=tmp_path / "state",
        source_path=external,
        source_bytes=None,
        generated_dir=cache,
    )
    assert snap.get("stable_path") is None
    assert bytes_match_render(data, collect_render_content_hashes(cache))


def test_should_preserve_existing_snapshot_when_session_active(tmp_path: Path):
    stable = tmp_path / "original_wallpaper.jpg"
    stable.write_bytes(b"\xff\xd8\xff\x00abc")
    existing = {"stable_path": str(stable), "content_hash": file_digest(stable.read_bytes())}
    assert should_preserve_existing_snapshot(existing, session_active=True, recovering=False)
    assert not should_preserve_existing_snapshot(existing, session_active=False, recovering=False)


def test_copy_file_to_stable_wallpaper_uses_original_wallpaper_basename(tmp_path: Path):
    source = tmp_path / "TranscodedWallpaper"
    source.write_bytes(b"\xff\xd8\xff\x00real")
    dest, digest = copy_file_to_stable_wallpaper(source, tmp_path / "state")
    assert dest.name == "original_wallpaper.jpg"
    assert dest.read_bytes() == source.read_bytes()
    assert digest == file_digest(source.read_bytes())


@pytest.mark.skipif(
    __import__("sys").platform != "win32",
    reason="Windows-only source priority",
)
def test_windows_source_priority_prefers_wallpaper_source_over_transcoded(tmp_path: Path):
    from unittest.mock import patch

    from now_playing_desktops.platforms.windows_restore import capture_windows_restore_snapshot

    registry_wall = tmp_path / "Pictures" / "real.jpg"
    registry_wall.parent.mkdir(parents=True)
    registry_wall.write_bytes(b"\xff\xd8\xff\x00registry-original")
    transcoded = tmp_path / "TranscodedWallpaper"
    transcoded.write_bytes(b"\xff\xd8\xff\x00transcoded-stale")

    with (
        patch(
            "now_playing_desktops.platforms.windows_restore._wallpaper_source_from_registry",
            return_value=registry_wall,
        ),
        patch(
            "now_playing_desktops.platforms.windows_restore._cached_files_wallpaper_path",
            return_value=None,
        ),
        patch(
            "now_playing_desktops.platforms.windows_restore._transcoded_wallpaper_path",
            return_value=transcoded,
        ),
        patch(
            "now_playing_desktops.platforms.windows_restore._read_desktop_style",
            return_value={"wallpaper_style": "10", "tile_wallpaper": "0"},
        ),
        patch(
            "now_playing_desktops.platforms.windows_restore._read_background_type",
            return_value=0,
        ),
    ):
        snap = capture_windows_restore_snapshot(
            state_dir=tmp_path / "state",
            generated_dir=None,
            reported_path=str(transcoded),
            per_monitor=False,
            monitor_paths={},
        )

    stable = Path(snap["stable_path"])
    assert stable.read_bytes() == registry_wall.read_bytes()
    assert snap["content_hash"] == file_digest(registry_wall.read_bytes())


@pytest.mark.skipif(
    __import__("sys").platform != "win32",
    reason="Windows-only restore bytes",
)
def test_restore_after_transcoded_overwritten_matches_stable_bytes(tmp_path: Path):
    from unittest.mock import MagicMock, patch

    from now_playing_desktops.platforms.windows_restore import (
        apply_windows_restore_snapshot,
        capture_windows_restore_snapshot,
        file_digest,
    )

    original = tmp_path / "real.jpg"
    original.write_bytes(b"\xff\xd8\xff\x00ORIGINAL_WALLPAPER_BYTES")
    transcoded = tmp_path / "TranscodedWallpaper"
    transcoded.write_bytes(original.read_bytes())

    with (
        patch(
            "now_playing_desktops.platforms.windows_restore._wallpaper_source_from_registry",
            return_value=original,
        ),
        patch(
            "now_playing_desktops.platforms.windows_restore._cached_files_wallpaper_path",
            return_value=None,
        ),
        patch(
            "now_playing_desktops.platforms.windows_restore._transcoded_wallpaper_path",
            return_value=transcoded,
        ),
        patch(
            "now_playing_desktops.platforms.windows_restore._read_desktop_style",
            return_value={"wallpaper_style": "10", "tile_wallpaper": "0"},
        ),
        patch(
            "now_playing_desktops.platforms.windows_restore._read_background_type",
            return_value=0,
        ),
    ):
        snap = capture_windows_restore_snapshot(
            state_dir=tmp_path / "state",
            generated_dir=tmp_path / "cache",
            reported_path=str(transcoded),
            per_monitor=False,
            monitor_paths={},
        )

    expected_hash = snap["content_hash"]
    album_bytes = b"\xff\xd8\xff\x00ALBUM_RENDER_WALLPAPER"
    transcoded.write_bytes(album_bytes)

    with patch(
        "now_playing_desktops.platforms.windows_restore.ctypes.windll.user32.SystemParametersInfoW",
        return_value=True,
    ):
        apply_windows_restore_snapshot(
            snap,
            set_wallpaper_on_monitor=MagicMock(),
            set_wallpaper_primary=MagicMock(),
        )

    stable = Path(snap["stable_path"])
    assert file_digest(stable.read_bytes()) == expected_hash
    assert stable.read_bytes() == original.read_bytes()
    assert transcoded.read_bytes() == album_bytes
