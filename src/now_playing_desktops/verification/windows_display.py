"""Simulate how Windows maps a wallpaper bitmap onto the physical desktop."""

from __future__ import annotations

from PIL import Image

from now_playing_desktops.platforms.windows_restore import (
    WALLPAPER_STYLE_CENTER,
    WALLPAPER_STYLE_FILL,
)

WALLPAPER_STYLE_STRETCH = "2"
WALLPAPER_STYLE_FIT = "6"


def _resize_cover(image: Image.Image, width: int, height: int) -> Image.Image:
    return image.resize((width, height), Image.Resampling.LANCZOS)


def simulate_wallpaper_on_display(
    wallpaper: Image.Image,
    *,
    display_width: int,
    display_height: int,
    wallpaper_style: str,
    fill_crop_from_top_left: bool = False,
) -> Image.Image:
    """
    Return the RGB pixels visible on a ``display_width`` x ``display_height`` monitor.

    ``fill_crop_from_top_left`` models the legacy DPI-unaware case where a smaller bitmap
    is scaled up and cropped from the origin instead of centered (observed on 150% laptops).
    """
    if display_width <= 0 or display_height <= 0:
        raise ValueError("display size must be positive")
    source = wallpaper.convert("RGB")
    iw, ih = source.size

    if wallpaper_style == WALLPAPER_STYLE_STRETCH:
        return _resize_cover(source, display_width, display_height)

    if wallpaper_style == WALLPAPER_STYLE_FIT:
        scale = min(display_width / iw, display_height / ih)
        new_w = max(1, int(round(iw * scale)))
        new_h = max(1, int(round(ih * scale)))
        fitted = _resize_cover(source, new_w, new_h)
        canvas = Image.new("RGB", (display_width, display_height), (0, 0, 0))
        paste_x = (display_width - new_w) // 2
        paste_y = (display_height - new_h) // 2
        canvas.paste(fitted, (paste_x, paste_y))
        return canvas

    if wallpaper_style == WALLPAPER_STYLE_CENTER:
        canvas = Image.new("RGB", (display_width, display_height), (0, 0, 0))
        paste_x = (display_width - iw) // 2
        paste_y = (display_height - ih) // 2
        canvas.paste(source, (paste_x, paste_y))
        return canvas

    if wallpaper_style == WALLPAPER_STYLE_FILL:
        scale = max(display_width / iw, display_height / ih)
        new_w = max(1, int(round(iw * scale)))
        new_h = max(1, int(round(ih * scale)))
        scaled = _resize_cover(source, new_w, new_h)
        if fill_crop_from_top_left:
            return scaled.crop((0, 0, display_width, display_height))
        left = (new_w - display_width) // 2
        top = (new_h - display_height) // 2
        return scaled.crop((left, top, left + display_width, top + display_height))

    raise ValueError(f"Unsupported wallpaper style {wallpaper_style!r}")


def simulate_dpi_unaware_fill_from_origin(
    wallpaper: Image.Image,
    *,
    display_width: int,
    display_height: int,
) -> Image.Image:
    """Scale a logical-size bitmap onto a larger physical desktop from the top-left origin."""
    source = wallpaper.convert("RGB")
    scale_x = display_width / source.width
    scale_y = display_height / source.height
    scaled = _resize_cover(
        source,
        max(1, int(round(source.width * scale_x))),
        max(1, int(round(source.height * scale_y))),
    )
    return scaled.crop((0, 0, display_width, display_height))
