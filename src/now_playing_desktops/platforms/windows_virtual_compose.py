"""Compose one virtual-desktop bitmap with a centered tile on each monitor (SPI Span fallback)."""

from __future__ import annotations

from PIL import Image, ImageDraw

from now_playing_desktops.composer import compose_wallpaper, plan_wallpaper_layout, render_backdrop
from now_playing_desktops.platforms.windows_monitors import MonitorInfo, compose_canvas_pixel_size


def virtual_desktop_origin(monitors: list[MonitorInfo]) -> tuple[int, int]:
    min_left = min(monitor.left for monitor in monitors)
    min_top = min(monitor.top for monitor in monitors)
    return min_left, min_top


def monitor_rect_on_canvas(
    monitor: MonitorInfo,
    *,
    origin_left: int,
    origin_top: int,
) -> tuple[int, int, int, int]:
    """Return ``(x0, y0, x1, y1)`` of a monitor on the virtual-desktop bitmap."""
    x0 = monitor.left - origin_left
    y0 = monitor.top - origin_top
    return x0, y0, x0 + monitor.width, y0 + monitor.height


def compose_virtual_desktop_wallpaper(
    cover: Image.Image,
    *,
    title: str,
    artist: str,
    monitors: list[MonitorInfo],
) -> Image.Image:
    """Build a Span-sized bitmap with one composed tile centered on each monitor."""
    if not monitors:
        raise ValueError("monitors must not be empty")
    origin_left, origin_top = virtual_desktop_origin(monitors)
    canvas_w, canvas_h = compose_canvas_pixel_size(monitors)
    backdrop = render_backdrop(cover, canvas_w, canvas_h)
    canvas = backdrop.convert("RGB")
    for monitor in monitors:
        tile = compose_wallpaper(
            cover,
            title=title,
            artist=artist,
            width=monitor.width,
            height=monitor.height,
        )
        x0, y0, _, _ = monitor_rect_on_canvas(
            monitor,
            origin_left=origin_left,
            origin_top=origin_top,
        )
        canvas.paste(tile, (x0, y0))
    return canvas


def panel_centers_on_virtual_canvas(
    cover: Image.Image,
    *,
    title: str,
    artist: str,
    monitors: list[MonitorInfo],
) -> list[tuple[float, float, MonitorInfo]]:
    """Return panel center ``(cx, cy, monitor)`` in virtual-desktop coordinates."""
    origin_left, origin_top = virtual_desktop_origin(monitors)
    centers: list[tuple[float, float, MonitorInfo]] = []
    for monitor in monitors:
        layout = plan_wallpaper_layout(
            cover,
            title=title,
            artist=artist,
            width=monitor.width,
            height=monitor.height,
        )
        px0, py0, px1, py1 = layout.panel
        cx = (px0 + px1) / 2
        cy = (py0 + py1) / 2
        x0, y0, _, _ = monitor_rect_on_canvas(
            monitor,
            origin_left=origin_left,
            origin_top=origin_top,
        )
        centers.append((x0 + cx, y0 + cy, monitor))
    return centers


def draw_monitor_outlines(
    image: Image.Image,
    monitors: list[MonitorInfo],
    *,
    origin_left: int | None = None,
    origin_top: int | None = None,
    outline: tuple[int, int, int] = (255, 64, 64),
    width: int = 4,
) -> Image.Image:
    """Return a copy with monitor rects outlined (for debugging artifacts)."""
    if origin_left is None or origin_top is None:
        origin_left, origin_top = virtual_desktop_origin(monitors)
    out = image.copy()
    draw = ImageDraw.Draw(out)
    for monitor in monitors:
        x0, y0, x1, y1 = monitor_rect_on_canvas(
            monitor,
            origin_left=origin_left,
            origin_top=origin_top,
        )
        for offset in range(width):
            draw.rectangle(
                (x0 + offset, y0 + offset, x1 - 1 - offset, y1 - 1 - offset),
                outline=outline,
            )
    return out
