from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from now_playing_desktops.wallpaper_state import WallpaperSessionState
from tests.helpers import make_runner


def test_crash_state_restore_applies_linux_snapshot(tmp_path: Path):
    state_path = tmp_path / "state.json"
    snapshot = {
        "backend": "gnome",
        "gsettings": {"picture-uri": "'file:///orig.png'"},
    }
    WallpaperSessionState(
        original_wallpaper_snapshot=snapshot,
        session_active=True,
        generated_wallpaper_dir=str(tmp_path / "cache"),
    ).save(state_path)

    platform = MagicMock()
    platform.apply_restore_snapshot = MagicMock()
    platform.get_current_wallpaper.return_value = None
    platform.list_screens.return_value = []
    platform.supports_per_screen_wallpaper.return_value = False
    platform.capture_restore_snapshot.return_value = snapshot

    runner = make_runner(tmp_path, platform=platform)
    runner.deps.state_path = state_path
    runner.startup()
    platform.apply_restore_snapshot.assert_called_once_with(snapshot)
    assert WallpaperSessionState.load(state_path).session_active is False
