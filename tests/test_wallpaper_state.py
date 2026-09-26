from pathlib import Path

from now_playing_desktops.wallpaper_state import (
    WallpaperSessionState,
    should_capture_as_original,
)


def test_should_capture_as_original_skips_generated_wallpaper(tmp_path: Path):
    generated = tmp_path / "cache"
    generated.mkdir()
    ours = generated / "composed.png"
    ours.write_bytes(b"x")
    assert should_capture_as_original(ours, generated_dir=generated, stored_original=None) is None


def test_should_capture_as_original_keeps_stored_original_when_current_is_generated(tmp_path: Path):
    generated = tmp_path / "cache"
    generated.mkdir()
    original = tmp_path / "original.jpg"
    original.write_bytes(b"o")
    ours = generated / "composed.png"
    ours.write_bytes(b"x")
    result = should_capture_as_original(
        ours,
        generated_dir=generated,
        stored_original=str(original),
    )
    assert result == original


def test_wallpaper_session_state_roundtrip(tmp_path: Path):
    path = tmp_path / "state.json"
    state = WallpaperSessionState(
        original_wallpaper_path="/tmp/wall.jpg",
        session_active=True,
        generated_wallpaper_dir="/tmp/cache",
    )
    state.save(path)
    loaded = WallpaperSessionState.load(path)
    assert loaded.original_wallpaper_path == "/tmp/wall.jpg"
    assert loaded.session_active is True
