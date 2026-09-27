from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from PIL import Image, ImageDraw, ImageFont

from now_playing_desktops.platforms.base import ScreenInfo
from now_playing_desktops.runner import NowPlayingRunner, RunnerDeps

ARTIFACTS_DIR = Path("/opt/cursor/artifacts")


def make_sample_cover(size: int = 640) -> Image.Image:
    """Colorful synthetic album art for sample PNG previews."""
    image = Image.new("RGB", (size, size))
    draw = ImageDraw.Draw(image)
    for y in range(size):
        for x in range(size):
            red = int(40 + (x / size) * 200)
            green = int(30 + (y / size) * 160)
            blue = int(120 + ((x + y) / (2 * size)) * 120)
            image.putpixel((x, y), (red % 256, green % 256, min(blue, 255)))
    draw.ellipse((40, 50, size - 60, size - 80), fill=(255, 210, 60))
    draw.rectangle(
        (size // 4, size // 3, size * 3 // 4, size * 2 // 3),
        outline=(255, 255, 255),
        width=6,
    )
    draw.polygon(
        [
            (size // 2, size // 5),
            (size * 4 // 5, size * 3 // 5),
            (size // 5, size * 3 // 5),
        ],
        fill=(220, 60, 140),
    )
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", size=size // 3)
    except OSError:
        font = ImageFont.load_default()
    draw.text((size // 2, size // 2), "N", font=font, fill=(255, 255, 255), anchor="mm")
    return image


def make_sharp_test_cover(size: int = 640) -> Image.Image:
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


def make_test_cover(size: int = 640) -> Image.Image:
    """Alias for the high-frequency cover used in sharpness assertions."""
    return make_sharp_test_cover(size)


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

    def list_screens(self) -> list[ScreenInfo]:
        return [
            ScreenInfo(
                screen_id="primary",
                width=self.screen[0],
                height=self.screen[1],
                is_primary=True,
            )
        ]

    def supports_per_screen_wallpaper(self) -> bool:
        return False

    def capture_restore_snapshot(self) -> dict:
        return {
            "backend": "fake",
            "path": str(self.wallpaper) if self.wallpaper else None,
        }

    def apply_restore_snapshot(self, snapshot: dict) -> None:
        raw = snapshot.get("path")
        if raw:
            path = Path(raw)
            if path.is_file():
                self.set_wallpaper(path)


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
