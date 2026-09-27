"""Shared helpers for cross-platform desktop verification runs."""

from __future__ import annotations

import hashlib
import inspect
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

from now_playing_desktops.composer import compose_wallpaper, plan_wallpaper_layout
from now_playing_desktops.platforms import autostart
from now_playing_desktops.platforms.windows_monitors import (
    MonitorInfo,
    compose_canvas_pixel_size,
)
from now_playing_desktops.spotify_art import TrackPlayback
from tests.helpers import ARTIFACTS_DIR, make_test_cover

VERIFY_TRACK = TrackPlayback(
    track_id="verify-track",
    art_url="https://example.test/art.jpg",
    title="Verify Title",
    artist="Verify Artist",
    is_playing=True,
)


def autostart_supports_env_file() -> bool:
    """True when PR #12-style autostart accepts ``env_file`` (not on older master)."""
    return "env_file" in inspect.signature(autostart.enable_autostart).parameters


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def panel_center_offset(
    image: Image.Image,
    *,
    width: int,
    height: int,
    title: str = VERIFY_TRACK.title,
    artist: str = VERIFY_TRACK.artist,
    cover: Image.Image | None = None,
) -> tuple[float, float]:
    """Return (dx, dy) from image center to glass panel center."""
    cover = cover or make_test_cover()
    layout = plan_wallpaper_layout(
        cover,
        title=title,
        artist=artist,
        width=width,
        height=height,
    )
    px0, py0, px1, py1 = layout.panel
    panel_cx = (px0 + px1) / 2
    panel_cy = (py0 + py1) / 2
    return abs(panel_cx - width / 2), abs(panel_cy - height / 2)


def assert_centered_within(
    image: Image.Image,
    width: int,
    height: int,
    tolerance: float = 2.0,
) -> tuple[float, float]:
    dx, dy = panel_center_offset(image, width=width, height=height)
    assert dx <= tolerance, f"horizontal offset {dx}px exceeds {tolerance}px"
    assert dy <= tolerance, f"vertical offset {dy}px exceeds {tolerance}px"
    return dx, dy


@dataclass(frozen=True)
class TwoMonitorLayout:
    name: str
    monitors: tuple[MonitorInfo, MonitorInfo]


def layout_monitors_negative_origin() -> TwoMonitorLayout:
    return TwoMonitorLayout(
        name="span-left",
        monitors=(
            MonitorInfo("1", 1920, 1080, True, left=0, top=0),
            MonitorInfo("2", 2560, 1440, False, left=-2560, top=-200),
        ),
    )


def layout_monitors_b_to_right() -> TwoMonitorLayout:
    return TwoMonitorLayout(
        name="span-right",
        monitors=(
            MonitorInfo("1", 1920, 1080, True, left=0, top=0),
            MonitorInfo("2", 2560, 1440, False, left=1920, top=0),
        ),
    )


def virtual_origin(monitors: list[MonitorInfo]) -> tuple[int, int]:
    return min(m.left for m in monitors), min(m.top for m in monitors)


def compose_virtual_desktop_span(
    monitors: list[MonitorInfo],
    *,
    track: TrackPlayback = VERIFY_TRACK,
    cover: Image.Image | None = None,
) -> Image.Image:
    cover = cover or make_test_cover()
    width, height = compose_canvas_pixel_size(monitors)
    return compose_wallpaper(
        cover,
        title=track.title,
        artist=track.artist,
        width=width,
        height=height,
    )


def monitor_rect_on_canvas(
    monitor: MonitorInfo,
    origin: tuple[int, int],
) -> tuple[int, int, int, int]:
    ox, oy = origin
    return (
        monitor.left - ox,
        monitor.top - oy,
        monitor.left - ox + monitor.width,
        monitor.top - oy + monitor.height,
    )


def draw_monitor_outlines(
    image: Image.Image,
    monitors: list[MonitorInfo],
    *,
    origin: tuple[int, int] | None = None,
) -> Image.Image:
    origin = origin or virtual_origin(monitors)
    outlined = image.copy()
    draw = ImageDraw.Draw(outlined)
    colors = ("#00ff88", "#ff4488")
    for index, monitor in enumerate(monitors):
        rect = monitor_rect_on_canvas(monitor, origin)
        draw.rectangle(rect, outline=colors[index % len(colors)], width=4)
    return outlined


def save_artifact(image: Image.Image, filename: str) -> Path:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    path = ARTIFACTS_DIR / filename
    image.save(path, format="PNG")
    return path


def capture_root_window(display: str, output_png: Path) -> None:
    output_png.parent.mkdir(parents=True, exist_ok=True)
    xwd_path = output_png.with_suffix(".xwd")
    env = {"DISPLAY": display}
    subprocess.run(
        ["xwd", "-root", "-out", str(xwd_path)],
        check=True,
        env=env,
        timeout=30,
    )
    subprocess.run(
        ["convert", str(xwd_path), str(output_png)],
        check=True,
        timeout=30,
    )
    xwd_path.unlink(missing_ok=True)
