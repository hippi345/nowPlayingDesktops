from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from PIL import Image, ImageDraw

from now_playing_desktops.runner import NowPlayingRunner, RunnerDeps

ARTIFACTS_DIR = Path("/opt/cursor/artifacts")


def make_test_cover(size: int = 640) -> Image.Image:
    """Album cover with a high-contrast checkerboard center for sharpness checks."""
    image = Image.new("RGB", (size, size), (25, 30, 90))
    draw = ImageDraw.Draw(image)
    square = size // 2
    origin = size // 4
    for y in range(origin, origin + square):
        for x in range(origin, origin + square):
            color = (240, 40, 40) if ((x // 16) + (y // 16)) % 2 == 0 else (40, 240, 40)
            draw.point((x, y), fill=color)
    return image


def image_variance(image: Image.Image, box: tuple[int, int, int, int]) -> float:
    crop = image.crop(box)
    pixels = list(crop.getdata())
    if not pixels:
        return 0.0
    values = [sum(px) / 3.0 for px in pixels]
    mean = sum(values) / len(values)
    return sum((v - mean) ** 2 for v in values) / len(values)


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
