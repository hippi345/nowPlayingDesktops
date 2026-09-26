from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from now_playing_desktops.runner import NowPlayingRunner, RunnerDeps


class FakePlatform:
    def __init__(
        self,
        wallpaper: Path | None = None,
        screen: tuple[int, int] = (1920, 1080),
    ) -> None:
        self.wallpaper = wallpaper
        self.screen = screen
        self.set_calls: list[Path] = []

    def set_wallpaper(self, path: Path) -> None:
        self.set_calls.append(path)
        self.wallpaper = path

    def get_current_wallpaper(self) -> Path | None:
        return self.wallpaper

    def get_primary_screen_size(self) -> tuple[int, int]:
        return self.screen


def make_runner(
    tmp_path: Path,
    *,
    platform: FakePlatform,
    sp: MagicMock | None = None,
    sleep: MagicMock | None = None,
    on_token_refresh: MagicMock | None = None,
) -> NowPlayingRunner:
    sp = sp or MagicMock()
    return NowPlayingRunner(
        RunnerDeps(
            platform=platform,
            sp=sp,
            cache_dir=tmp_path / "cache",
            state_path=tmp_path / "state.json",
            poll_interval_seconds=2.5,
            on_token_refresh=on_token_refresh,
            sleep=sleep,
        )
    )
