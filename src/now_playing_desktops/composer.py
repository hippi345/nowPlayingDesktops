"""Compose desktop wallpapers from album art and track metadata."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from now_playing_desktops.config import FOREGROUND_HEIGHT_RATIO, MAX_COVER_UPSCALE

TITLE_HEIGHT_RATIO = 0.024
ARTIST_HEIGHT_RATIO = 0.017
TEXT_WIDTH_COVER_FACTOR = 1.6
TEXT_WIDTH_SCREEN_FACTOR = 0.8
ELLIPSIS = "…"

_FONT_CANDIDATES = (
    "DejaVuSans.ttf",
    "Arial.ttf",
    "Segoe UI.ttf",
    "Helvetica.ttc",
)


@dataclass(frozen=True)
class TextLayout:
    title: str
    artist: str
    title_font_size: int
    artist_font_size: int
    max_width: int


def load_wallpaper_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load the sans-serif font used for wallpaper track labels."""
    return _load_font(size)


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in _FONT_CANDIDATES:
        for directory in (
            Path("/usr/share/fonts/truetype/dejavu"),
            Path("/usr/share/fonts/truetype/liberation"),
            Path("/System/Library/Fonts/Supplemental"),
            Path("C:/Windows/Fonts"),
        ):
            candidate = directory / name
            if candidate.is_file():
                try:
                    return ImageFont.truetype(str(candidate), size=size)
                except OSError:
                    continue
        try:
            return ImageFont.truetype(name, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def title_font_size_for_height(height: int) -> int:
    return max(12, int(round(height * TITLE_HEIGHT_RATIO)))


def artist_font_size_for_height(height: int) -> int:
    return max(10, int(round(height * ARTIST_HEIGHT_RATIO)))


def max_text_width(foreground_width: int, screen_width: int) -> int:
    from_cover = int(foreground_width * TEXT_WIDTH_COVER_FACTOR)
    from_screen = int(screen_width * TEXT_WIDTH_SCREEN_FACTOR)
    return min(from_cover, from_screen)


def ellipsize(text: str, font: ImageFont.ImageFont, max_width: int) -> str:
    if not text:
        return ""
    if font.getlength(text) <= max_width:
        return text
    trimmed = text
    while trimmed and font.getlength(trimmed + ELLIPSIS) > max_width:
        trimmed = trimmed[:-1]
    return (trimmed + ELLIPSIS) if trimmed else ELLIPSIS


def compute_text_layout(
    *,
    title: str,
    artist: str,
    screen_width: int,
    screen_height: int,
    foreground_width: int,
) -> TextLayout:
    title_size = title_font_size_for_height(screen_height)
    artist_size = artist_font_size_for_height(screen_height)
    title_font = _load_font(title_size)
    artist_font = _load_font(artist_size)
    limit = max_text_width(foreground_width, screen_width)
    return TextLayout(
        title=ellipsize(title, title_font, limit),
        artist=ellipsize(artist, artist_font, limit),
        title_font_size=title_size,
        artist_font_size=artist_size,
        max_width=limit,
    )


def scale_cover_to_fill(cover: Image.Image, width: int, height: int) -> Image.Image:
    """Scale ``cover`` with cover-fit (max scale) and center-crop to ``width`` x ``height``."""
    scale = max(width / cover.width, height / cover.height)
    new_w = max(1, int(round(cover.width * scale)))
    new_h = max(1, int(round(cover.height * scale)))
    resized = cover.resize((new_w, new_h), Image.Resampling.LANCZOS)
    left = (new_w - width) // 2
    top = (new_h - height) // 2
    return resized.crop((left, top, left + width, top + height))


def _rounded_rectangle_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, size[0], size[1]), radius=radius, fill=255)
    return mask


def _build_backdrop(cover: Image.Image, width: int, height: int) -> Image.Image:
    backdrop = scale_cover_to_fill(cover.convert("RGB"), width, height)
    blur_radius = max(24, min(width, height) // 40)
    backdrop = backdrop.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    darken = Image.new("RGB", (width, height), (0, 0, 0))
    return Image.blend(backdrop, darken, alpha=0.45)


def _foreground_cover(cover: Image.Image, width: int, height: int) -> Image.Image:
    target_height = max(1, int(height * FOREGROUND_HEIGHT_RATIO))
    scale_for_height = target_height / cover.height
    scale = min(scale_for_height, MAX_COVER_UPSCALE)
    if scale < 1.0:
        new_size = (max(1, int(cover.width * scale)), max(1, int(cover.height * scale)))
        return cover.resize(new_size, Image.Resampling.LANCZOS)
    if scale > 1.0:
        capped = min(scale, MAX_COVER_UPSCALE)
        if capped > 1.0:
            new_size = (max(1, int(cover.width * capped)), max(1, int(cover.height * capped)))
            return cover.resize(new_size, Image.Resampling.LANCZOS)
    return cover.copy()


def compose_wallpaper(
    cover: Image.Image,
    *,
    title: str,
    artist: str,
    width: int,
    height: int,
) -> Image.Image:
    """Build a wallpaper image at ``width`` x ``height``."""
    canvas = _build_backdrop(cover, width, height)
    foreground = _foreground_cover(cover.convert("RGBA"), width, height)
    layout = compute_text_layout(
        title=title,
        artist=artist,
        screen_width=width,
        screen_height=height,
        foreground_width=foreground.width,
    )
    title_font = _load_font(layout.title_font_size)
    artist_font = _load_font(layout.artist_font_size)
    title_text = layout.title
    artist_text = layout.artist

    corner_radius = max(12, min(foreground.width, foreground.height) // 30)
    mask = _rounded_rectangle_mask(foreground.size, corner_radius)
    shadow_offset = max(6, min(width, height) // 200)
    shadow_blur = max(10, min(width, height) // 120)
    shadow = Image.new("RGBA", foreground.size, (0, 0, 0, 180))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=shadow_blur))

    title_bbox = title_font.getbbox(title_text)
    artist_bbox = artist_font.getbbox(artist_text)
    title_h = title_bbox[3] - title_bbox[1]
    artist_h = artist_bbox[3] - artist_bbox[1]
    text_block_height = title_h + artist_h + height // 40
    total_height = foreground.height + text_block_height + height // 16
    top_y = (height - total_height) // 2
    fg_x = (width - foreground.width) // 2
    fg_y = top_y

    shadow_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    shadow_layer.paste(
        shadow,
        (fg_x + shadow_offset, fg_y + shadow_offset),
        mask,
    )
    canvas = Image.alpha_composite(canvas.convert("RGBA"), shadow_layer)

    fg_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    fg_layer.paste(foreground, (fg_x, fg_y), mask)
    canvas = Image.alpha_composite(canvas, fg_layer)

    draw = ImageDraw.Draw(canvas)
    text_y = fg_y + foreground.height + height // 32
    draw.text((width // 2, text_y), title_text, font=title_font, fill="white", anchor="mt")
    draw.text(
        (width // 2, text_y + title_h + height // 80),
        artist_text,
        font=artist_font,
        fill=(230, 230, 230),
        anchor="mt",
    )
    return canvas.convert("RGB")


def save_wallpaper(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() in {".jpg", ".jpeg"}:
        image.save(path, format="JPEG", quality=95, optimize=True)
    else:
        image.save(path, format="PNG", optimize=True)
