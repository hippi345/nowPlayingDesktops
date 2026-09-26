"""Compose desktop wallpapers from album art and track metadata."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from now_playing_desktops.config import FOREGROUND_HEIGHT_RATIO, MAX_COVER_UPSCALE

_FONT_CANDIDATES = (
    "DejaVuSans.ttf",
    "Arial.ttf",
    "Segoe UI.ttf",
    "Helvetica.ttc",
)


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


def _ellipsize(text: str, font: ImageFont.ImageFont, max_width: int) -> str:
    if not text:
        return ""
    if font.getlength(text) <= max_width:
        return text
    ellipsis = "…"
    trimmed = text
    while trimmed and font.getlength(trimmed + ellipsis) > max_width:
        trimmed = trimmed[:-1]
    return (trimmed + ellipsis) if trimmed else ellipsis


def _rounded_rectangle_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, size[0], size[1]), radius=radius, fill=255)
    return mask


def _build_backdrop(cover: Image.Image, width: int, height: int) -> Image.Image:
    backdrop = cover.copy().convert("RGB")
    backdrop_ratio = backdrop.width / backdrop.height
    screen_ratio = width / height
    if backdrop_ratio > screen_ratio:
        new_height = height
        new_width = int(new_height * backdrop_ratio)
    else:
        new_width = width
        new_height = int(new_width / backdrop_ratio)
    backdrop = backdrop.resize((new_width, new_height), Image.Resampling.LANCZOS)
    left = (new_width - width) // 2
    top = (new_height - height) // 2
    backdrop = backdrop.crop((left, top, left + width, top + height))
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
    corner_radius = max(12, min(foreground.width, foreground.height) // 30)
    mask = _rounded_rectangle_mask(foreground.size, corner_radius)
    shadow_offset = max(6, min(width, height) // 200)
    shadow_blur = max(10, min(width, height) // 120)
    shadow = Image.new("RGBA", foreground.size, (0, 0, 0, 180))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=shadow_blur))

    title_font = _load_font(max(22, height // 42))
    artist_font = _load_font(max(18, height // 52))
    title_text = _ellipsize(title, title_font, int(width * 0.82))
    artist_text = _ellipsize(artist, artist_font, int(width * 0.82))
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
        (width // 2, text_y + (title_bbox[3] - title_bbox[1]) + height // 80),
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
