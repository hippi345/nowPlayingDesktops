"""Compose desktop wallpapers from album art and track metadata."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from now_playing_desktops.config import FOREGROUND_HEIGHT_RATIO, MAX_COVER_UPSCALE

# --- Typography ---
TITLE_HEIGHT_RATIO = 0.024
ARTIST_HEIGHT_RATIO = 0.017
TEXT_WIDTH_COVER_FACTOR = 1.6
TEXT_WIDTH_SCREEN_FACTOR = 0.8
ELLIPSIS = "…"
TEXT_SHADOW_OFFSET_Y = 3
TEXT_SHADOW_ALPHA = 210
TEXT_STROKE_WIDTH = 1

# --- Backdrop ---
BACKDROP_BLUR_MIN_PX = 36
BACKDROP_BLUR_SCREEN_DIVISOR = 14
BACKDROP_DARKEN_BLEND = 0.52
BACKDROP_BRIGHTNESS = 1.0 - BACKDROP_DARKEN_BLEND

# --- Vignette ---
VIGNETTE_STRENGTH = 0.58
VIGNETTE_POWER = 1.6
VIGNETTE_MASK_SIZE = 256

# --- Cover frame ---
COVER_CORNER_RADIUS_DIVISOR = 30
RIM_HIGHLIGHT_WIDTH_1080P = 2
RIM_HIGHLIGHT_ALPHA = 150
RIM_HIGHLIGHT_SCREEN_HEIGHT_REF = 1080

# --- Layered cover shadow (contact + ambient) ---
COVER_SHADOW_CONTACT_OFFSET_Y_FRAC = 0.016
COVER_SHADOW_CONTACT_BLUR_FRAC = 0.05
COVER_SHADOW_CONTACT_ALPHA = 230
COVER_SHADOW_AMBIENT_OFFSET_Y_FRAC = 0.065
COVER_SHADOW_AMBIENT_BLUR_FRAC = 0.2
COVER_SHADOW_AMBIENT_ALPHA = 200
COVER_SHADOW_AMBIENT_PAD_FRAC = 0.24

# --- Dominant-color glow behind cover ---
GLOW_BLUR_FRAC = 0.22
GLOW_ALPHA = 42
GLOW_SCALE_FRAC = 1.12
GLOW_UPWARD_BIAS_FRAC = 0.06

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


@dataclass(frozen=True)
class CoverPlacement:
    x: int
    y: int
    width: int
    height: int
    corner_radius: int


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


def backdrop_blur_radius(width: int, height: int) -> float:
    return max(BACKDROP_BLUR_MIN_PX, min(width, height) / BACKDROP_BLUR_SCREEN_DIVISOR)


def scale_cover_to_fill(cover: Image.Image, width: int, height: int) -> Image.Image:
    """Scale ``cover`` with cover-fit (max scale) and center-crop to ``width`` x ``height``."""
    scale = max(width / cover.width, height / cover.height)
    new_w = max(1, int(round(cover.width * scale)))
    new_h = max(1, int(round(cover.height * scale)))
    resized = cover.resize((new_w, new_h), Image.Resampling.LANCZOS)
    left = (new_w - width) // 2
    top = (new_h - height) // 2
    return resized.crop((left, top, left + width, top + height))


def _vignette_mask(width: int, height: int) -> Image.Image:
    small_h = max(1, int(VIGNETTE_MASK_SIZE * height / width))
    mask = Image.new("L", (VIGNETTE_MASK_SIZE, small_h))
    cx = VIGNETTE_MASK_SIZE / 2
    cy = small_h / 2
    pixels = mask.load()
    for y in range(small_h):
        for x in range(VIGNETTE_MASK_SIZE):
            nx = (x - cx) / cx
            ny = (y - cy) / cy if cy else 0
            r = min(1.0, (nx * nx + ny * ny) ** 0.5)
            strength = r**VIGNETTE_POWER
            pixels[x, y] = max(0, min(255, int(255 * (1 - VIGNETTE_STRENGTH * strength))))
    return mask.resize((width, height), Image.Resampling.BILINEAR)


def apply_vignette(image: Image.Image) -> Image.Image:
    mask = _vignette_mask(*image.size)
    dark = Image.new("RGB", image.size, (0, 0, 0))
    return Image.composite(image, dark, mask)


def render_backdrop(cover: Image.Image, width: int, height: int) -> Image.Image:
    """Blur, darken, and vignette the fill-scaled cover (no foreground)."""
    backdrop = scale_cover_to_fill(cover.convert("RGB"), width, height)
    backdrop = backdrop.filter(ImageFilter.GaussianBlur(radius=backdrop_blur_radius(width, height)))
    darken = Image.new("RGB", (width, height), (0, 0, 0))
    backdrop = Image.blend(backdrop, darken, alpha=BACKDROP_DARKEN_BLEND)
    return apply_vignette(backdrop)


def extract_dominant_glow_color(cover: Image.Image) -> tuple[int, int, int]:
    """Pick a vivid average color from the cover for the rear glow tint."""
    small = cover.convert("RGB").resize((64, 64))
    best_color = (160, 120, 200)
    best_score = -1.0
    for r, g, b in small.getdata():
        mx = max(r, g, b)
        mn = min(r, g, b)
        if mx < 32:
            continue
        saturation = mx - mn
        vivid = saturation * (mx / 255.0)
        if vivid > best_score:
            best_score = vivid
            best_color = (r, g, b)
    return best_color


def mean_luminance(image: Image.Image, box: tuple[int, int, int, int]) -> float:
    crop = image.crop(box)
    total = 0.0
    pixels = list(crop.getdata())
    if not pixels:
        return 0.0
    for r, g, b in pixels:
        total += 0.2126 * r + 0.7152 * g + 0.0722 * b
    return total / len(pixels)


def relative_luminance(rgb: tuple[int, int, int]) -> float:
    def channel(value: int) -> float:
        c = value / 255.0
        if c <= 0.03928:
            return c / 12.92
        return ((c + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast_ratio(foreground: tuple[int, int, int], background: tuple[int, int, int]) -> float:
    l1 = relative_luminance(foreground)
    l2 = relative_luminance(background)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _rounded_rectangle_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, size[0], size[1]), radius=radius, fill=255)
    return mask


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


def _cover_placement(
    foreground: Image.Image,
    width: int,
    height: int,
    screen_height: int,
) -> CoverPlacement:
    corner_radius = max(12, min(foreground.width, foreground.height) // COVER_CORNER_RADIUS_DIVISOR)
    title_font = _load_font(title_font_size_for_height(screen_height))
    artist_font = _load_font(artist_font_size_for_height(screen_height))
    title_h = title_font.getbbox("Ag")[3] - title_font.getbbox("Ag")[1]
    artist_h = artist_font.getbbox("Ag")[3] - artist_font.getbbox("Ag")[1]
    text_block_height = title_h + artist_h + height // 40
    total_height = foreground.height + text_block_height + height // 16
    top_y = (height - total_height) // 2
    fg_x = (width - foreground.width) // 2
    return CoverPlacement(
        x=fg_x,
        y=top_y,
        width=foreground.width,
        height=foreground.height,
        corner_radius=corner_radius,
    )


def _build_glow_layer(
    color: tuple[int, int, int],
    placement: CoverPlacement,
    canvas_size: tuple[int, int],
) -> Image.Image:
    glow_w = int(placement.width * GLOW_SCALE_FRAC)
    glow_h = int(placement.height * GLOW_SCALE_FRAC)
    blur = max(12, int(placement.height * GLOW_BLUR_FRAC))
    glow = Image.new("RGBA", (glow_w, glow_h), (*color, GLOW_ALPHA))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=blur))
    layer = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    gx = placement.x + (placement.width - glow_w) // 2
    upward = int(placement.height * GLOW_UPWARD_BIAS_FRAC)
    gy = placement.y + (placement.height - glow_h) // 2 - upward
    layer.paste(glow, (gx, gy), glow)
    return layer


def _build_layered_shadow_layer(
    placement: CoverPlacement,
    canvas_size: tuple[int, int],
) -> Image.Image:
    mask = _rounded_rectangle_mask((placement.width, placement.height), placement.corner_radius)
    layer = Image.new("RGBA", canvas_size, (0, 0, 0, 0))

    contact_blur = max(4, int(placement.height * COVER_SHADOW_CONTACT_BLUR_FRAC))
    contact_offset_y = max(2, int(placement.height * COVER_SHADOW_CONTACT_OFFSET_Y_FRAC))
    contact_size = (placement.width, placement.height)
    contact = Image.new("RGBA", contact_size, (0, 0, 0, COVER_SHADOW_CONTACT_ALPHA))
    contact = contact.filter(ImageFilter.GaussianBlur(radius=contact_blur))
    layer.paste(contact, (placement.x, placement.y + contact_offset_y), mask)

    pad = int(placement.height * COVER_SHADOW_AMBIENT_PAD_FRAC)
    ambient_w = placement.width + pad * 2
    ambient_h = placement.height + pad * 2
    ambient_blur = max(8, int(placement.height * COVER_SHADOW_AMBIENT_BLUR_FRAC))
    ambient_offset_y = max(4, int(placement.height * COVER_SHADOW_AMBIENT_OFFSET_Y_FRAC))
    ambient_radius = placement.corner_radius + pad // 3
    ambient_mask = _rounded_rectangle_mask((ambient_w, ambient_h), ambient_radius)
    ambient = Image.new("RGBA", (ambient_w, ambient_h), (0, 0, 0, COVER_SHADOW_AMBIENT_ALPHA))
    ambient = ambient.filter(ImageFilter.GaussianBlur(radius=ambient_blur))
    layer.paste(
        ambient,
        (placement.x - pad, placement.y - pad // 2 + ambient_offset_y),
        ambient_mask,
    )
    return layer


def _rim_highlight_width(screen_height: int) -> int:
    scale = screen_height / RIM_HIGHLIGHT_SCREEN_HEIGHT_REF
    return max(1, round(RIM_HIGHLIGHT_WIDTH_1080P * scale))


def _draw_rim_highlight(
    canvas: Image.Image,
    placement: CoverPlacement,
    screen_height: int,
) -> Image.Image:
    layer = canvas.convert("RGBA")
    draw = ImageDraw.Draw(layer)
    inset = _rim_highlight_width(screen_height) // 2
    draw.rounded_rectangle(
        (
            placement.x + inset,
            placement.y + inset,
            placement.x + placement.width - inset - 1,
            placement.y + placement.height - inset - 1,
        ),
        radius=max(1, placement.corner_radius - inset),
        outline=(255, 255, 255, RIM_HIGHLIGHT_ALPHA),
        width=_rim_highlight_width(screen_height),
    )
    return layer


def _draw_text_with_shadow(
    canvas: Image.Image,
    *,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
) -> Image.Image:
    layer = canvas.convert("RGBA")
    draw = ImageDraw.Draw(layer)
    x, y = xy
    shadow_y = y + TEXT_SHADOW_OFFSET_Y
    draw.text(
        (x, shadow_y),
        text,
        font=font,
        fill=(0, 0, 0, TEXT_SHADOW_ALPHA),
        anchor="mt",
        stroke_width=TEXT_STROKE_WIDTH,
        stroke_fill=(0, 0, 0, TEXT_SHADOW_ALPHA),
    )
    draw.text(
        (x, y),
        text,
        font=font,
        fill=fill,
        anchor="mt",
        stroke_width=TEXT_STROKE_WIDTH,
        stroke_fill=(0, 0, 0, 140),
    )
    return layer


def compute_cover_placement(cover: Image.Image, width: int, height: int) -> CoverPlacement:
    foreground = _foreground_cover(cover.convert("RGBA"), width, height)
    return _cover_placement(foreground, width, height, height)


def compose_wallpaper(
    cover: Image.Image,
    *,
    title: str,
    artist: str,
    width: int,
    height: int,
) -> Image.Image:
    """Build a wallpaper image at ``width`` x ``height``."""
    canvas = render_backdrop(cover, width, height).convert("RGBA")
    foreground = _foreground_cover(cover.convert("RGBA"), width, height)
    placement = _cover_placement(foreground, width, height, height)
    layout = compute_text_layout(
        title=title,
        artist=artist,
        screen_width=width,
        screen_height=height,
        foreground_width=foreground.width,
    )
    title_font = _load_font(layout.title_font_size)
    artist_font = _load_font(layout.artist_font_size)
    mask = _rounded_rectangle_mask(foreground.size, placement.corner_radius)

    glow_color = extract_dominant_glow_color(cover)
    canvas = Image.alpha_composite(
        canvas,
        _build_glow_layer(glow_color, placement, (width, height)),
    )
    canvas = Image.alpha_composite(
        canvas,
        _build_layered_shadow_layer(placement, (width, height)),
    )

    fg_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    fg_layer.paste(foreground, (placement.x, placement.y), mask)
    canvas = Image.alpha_composite(canvas, fg_layer)
    canvas = _draw_rim_highlight(canvas, placement, height)

    title_bbox = title_font.getbbox(layout.title)
    title_h = title_bbox[3] - title_bbox[1]
    text_y = placement.y + placement.height + height // 32
    canvas = _draw_text_with_shadow(
        canvas,
        xy=(width // 2, text_y),
        text=layout.title,
        font=title_font,
        fill=(255, 255, 255),
    )
    canvas = _draw_text_with_shadow(
        canvas,
        xy=(width // 2, text_y + title_h + height // 80),
        text=layout.artist,
        font=artist_font,
        fill=(230, 230, 230),
    )
    return canvas.convert("RGB")


def save_wallpaper(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() in {".jpg", ".jpeg"}:
        image.save(path, format="JPEG", quality=95, optimize=True)
    else:
        image.save(path, format="PNG", optimize=True)
