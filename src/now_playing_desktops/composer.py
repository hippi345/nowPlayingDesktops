"""Compose desktop wallpapers from album art and track metadata."""

from __future__ import annotations

import importlib.resources
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from now_playing_desktops.config import FOREGROUND_HEIGHT_RATIO, MAX_COVER_UPSCALE

# --- Typography ---
TITLE_HEIGHT_RATIO = 0.024
ARTIST_HEIGHT_RATIO = 0.017
TEXT_WIDTH_COVER_FACTOR = 1.6
TEXT_WIDTH_SCREEN_FACTOR = 0.8
ELLIPSIS = "…"
TEXT_SUPERSAMPLE_FACTOR = 3
ARTIST_TEXT_ALPHA = int(255 * 0.85)
ARTIST_TEXT_RGB = (255, 255, 255)
TITLE_FONT_FILE = "Inter-Bold.ttf"
ARTIST_FONT_FILE = "Inter-Medium.ttf"
TEXT_LINE_GAP_DIVISOR = 48
TEXT_BLOCK_GAP_DIVISOR = 40

# --- Backdrop ---
BACKDROP_BLUR_MIN_PX = 36
BACKDROP_BLUR_SCREEN_DIVISOR = 14
BACKDROP_DARKEN_BLEND = 0.52
BACKDROP_BRIGHTNESS = 1.0 - BACKDROP_DARKEN_BLEND

# --- Vignette ---
VIGNETTE_STRENGTH = 0.58
VIGNETTE_POWER = 1.6
VIGNETTE_MASK_SIZE = 256

# --- Glass panel ("liquid glass") ---
GLASS_PANEL_PADDING_DIVISOR = 26
GLASS_CORNER_RADIUS_SHORT_SIDE_FRAC = 0.048
GLASS_BACKDROP_EXTRA_BLUR_DIVISOR = 22
GLASS_TINT_RGB = (22, 24, 32)
GLASS_TINT_ALPHA = 102
GLASS_SATURATION_BOOST = 1.22
GLASS_INNER_BORDER_ALPHA = 48
GLASS_INNER_BORDER_WIDTH_REF = 1
GLASS_INNER_BORDER_SCREEN_HEIGHT_REF = 1080
GLASS_SPECULAR_TOP_ALPHA = 44
GLASS_SPECULAR_HEIGHT_FRAC = 0.32
GLASS_DROP_SHADOW_BLUR_FRAC = 0.042
GLASS_DROP_SHADOW_OFFSET_FRAC = 0.01
GLASS_DROP_SHADOW_ALPHA = 92

# --- Cover frame ---
COVER_CORNER_RADIUS_DIVISOR = 30
RIM_HIGHLIGHT_WIDTH_1080P = 2
RIM_HIGHLIGHT_ALPHA = 150
RIM_HIGHLIGHT_SCREEN_HEIGHT_REF = 1080

# --- Layered cover shadow (contact + ambient) ---
COVER_SHADOW_CONTACT_OFFSET_Y_FRAC = 0.016
COVER_SHADOW_CONTACT_BLUR_FRAC = 0.05
COVER_SHADOW_CONTACT_ALPHA = 150
COVER_SHADOW_AMBIENT_OFFSET_Y_FRAC = 0.065
COVER_SHADOW_AMBIENT_BLUR_FRAC = 0.2
COVER_SHADOW_AMBIENT_ALPHA = 110
COVER_SHADOW_AMBIENT_PAD_FRAC = 0.24

# --- Dominant-color glow behind cover ---
GLOW_BLUR_FRAC = 0.22
GLOW_ALPHA = 42
GLOW_SCALE_FRAC = 1.12
GLOW_UPWARD_BIAS_FRAC = 0.06

_FONTS_PACKAGE = "now_playing_desktops.fonts"


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


@dataclass(frozen=True)
class GlassContrastAdaptation:
    tint_rgb: tuple[int, int, int]
    tint_alpha: int
    inner_border_alpha: int
    specular_top_alpha: int
    fill_lift_alpha: int
    rim_highlight_alpha: int


def _glass_contrast_adaptation(backdrop_luminance: float) -> GlassContrastAdaptation:
    """Boost panel lift and edges when the blurred backdrop behind the panel is very dark."""
    if backdrop_luminance >= 52.0:
        return GlassContrastAdaptation(
            tint_rgb=GLASS_TINT_RGB,
            tint_alpha=GLASS_TINT_ALPHA,
            inner_border_alpha=GLASS_INNER_BORDER_ALPHA,
            specular_top_alpha=GLASS_SPECULAR_TOP_ALPHA,
            fill_lift_alpha=0,
            rim_highlight_alpha=RIM_HIGHLIGHT_ALPHA,
        )
    strength = min(1.0, max(0.0, (52.0 - backdrop_luminance) / 52.0))
    tint_r = int(GLASS_TINT_RGB[0] + (72 - GLASS_TINT_RGB[0]) * strength)
    tint_g = int(GLASS_TINT_RGB[1] + (78 - GLASS_TINT_RGB[1]) * strength)
    tint_b = int(GLASS_TINT_RGB[2] + (96 - GLASS_TINT_RGB[2]) * strength)
    return GlassContrastAdaptation(
        tint_rgb=(tint_r, tint_g, tint_b),
        tint_alpha=int(GLASS_TINT_ALPHA + 55 * strength),
        inner_border_alpha=int(GLASS_INNER_BORDER_ALPHA + 90 * strength),
        specular_top_alpha=int(GLASS_SPECULAR_TOP_ALPHA + 40 * strength),
        fill_lift_alpha=int(18 + 40 * strength),
        rim_highlight_alpha=int(RIM_HIGHLIGHT_ALPHA + 70 * strength),
    )


@dataclass(frozen=True)
class WallpaperLayout:
    """Pixel rectangles (left, top, right, bottom) for centering tests."""

    panel: tuple[int, int, int, int]
    cover: tuple[int, int, int, int]
    title: tuple[int, int, int, int]
    artist: tuple[int, int, int, int]


def load_wallpaper_font(
    size: int,
    *,
    bold: bool = True,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load the bundled Inter font used for wallpaper track labels."""
    return _load_package_font(TITLE_FONT_FILE if bold else ARTIST_FONT_FILE, size)


def _font_path(filename: str) -> Path:
    with importlib.resources.as_file(
        importlib.resources.files(_FONTS_PACKAGE) / filename,
    ) as path:
        return Path(path)


def _load_package_font(filename: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(str(_font_path(filename)), size=size)
    except OSError:
        return ImageFont.load_default()


def _load_font(size: int, *, bold: bool = True) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return _load_package_font(TITLE_FONT_FILE if bold else ARTIST_FONT_FILE, size)


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
    title_font = _load_font(title_size, bold=True)
    artist_font = _load_font(artist_size, bold=False)
    limit = max_text_width(foreground_width, screen_width)
    return TextLayout(
        title=ellipsize(title, title_font, limit),
        artist=ellipsize(artist, artist_font, limit),
        title_font_size=title_size,
        artist_font_size=artist_size,
        max_width=limit,
    )


def _text_bbox(
    text: str,
    font: ImageFont.ImageFont,
    *,
    anchor: str = "mt",
) -> tuple[int, int, int, int]:
    probe = Image.new("RGBA", (4, 4))
    draw = ImageDraw.Draw(probe)
    return draw.textbbox((0, 0), text, font=font, anchor=anchor)


def _scale_for_height(screen_height: int, ref: int, value: int) -> int:
    return max(1, round(value * screen_height / ref))


def _glass_corner_radius(panel_w: int, panel_h: int) -> int:
    short = min(panel_w, panel_h)
    return max(12, int(round(short * GLASS_CORNER_RADIUS_SHORT_SIDE_FRAC)))


def _panel_padding(screen_height: int) -> int:
    return max(16, screen_height // GLASS_PANEL_PADDING_DIVISOR)


def backdrop_blur_radius(width: int, height: int) -> float:
    return max(BACKDROP_BLUR_MIN_PX, min(width, height) / BACKDROP_BLUR_SCREEN_DIVISOR)


def scale_cover_to_fill(cover: Image.Image, width: int, height: int) -> Image.Image:
    """Scale ``cover`` with cover-fit (max scale) and center-crop to ``width`` x ``height``."""
    if width <= 0 or height <= 0:
        raise ValueError(f"Wallpaper size must be positive, got {width}x{height}")
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
    w, h = size
    draw.rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=255)
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


def plan_wallpaper_layout(
    cover: Image.Image,
    *,
    title: str,
    artist: str,
    width: int,
    height: int,
) -> WallpaperLayout:
    """Compute panel, cover, and text rectangles with centered padding."""
    foreground = _foreground_cover(cover.convert("RGBA"), width, height)
    layout = compute_text_layout(
        title=title,
        artist=artist,
        screen_width=width,
        screen_height=height,
        foreground_width=foreground.width,
    )
    title_font = _load_font(layout.title_font_size, bold=True)
    artist_font = _load_font(layout.artist_font_size, bold=False)
    title_bb = _text_bbox(layout.title, title_font, anchor="mt")
    artist_bb = _text_bbox(layout.artist, artist_font, anchor="mt")
    title_w = title_bb[2] - title_bb[0]
    title_h = title_bb[3] - title_bb[1]
    artist_w = artist_bb[2] - artist_bb[0]
    artist_h = artist_bb[3] - artist_bb[1]
    text_block_w = max(title_w, artist_w)
    line_gap = max(4, height // TEXT_LINE_GAP_DIVISOR)
    block_gap = max(8, height // TEXT_BLOCK_GAP_DIVISOR)
    text_block_h = title_h + line_gap + artist_h
    pad = _panel_padding(height)
    panel_w = max(foreground.width, text_block_w) + pad * 2
    panel_h = foreground.height + block_gap + text_block_h + pad * 2
    panel_x = (width - panel_w) // 2
    panel_y = (height - panel_h) // 2
    cover_x = panel_x + (panel_w - foreground.width) // 2
    cover_y = panel_y + pad
    text_center_x = panel_x + panel_w // 2
    title_top = cover_y + foreground.height + block_gap
    artist_top = title_top + title_h + line_gap
    title_rect = (
        text_center_x + title_bb[0],
        title_top + title_bb[1],
        text_center_x + title_bb[2],
        title_top + title_bb[3],
    )
    artist_rect = (
        text_center_x + artist_bb[0],
        artist_top + artist_bb[1],
        text_center_x + artist_bb[2],
        artist_top + artist_bb[3],
    )
    cover_rect = (cover_x, cover_y, cover_x + foreground.width, cover_y + foreground.height)
    panel_rect = (panel_x, panel_y, panel_x + panel_w, panel_y + panel_h)
    return WallpaperLayout(panel=panel_rect, cover=cover_rect, title=title_rect, artist=artist_rect)


def compute_cover_placement(cover: Image.Image, width: int, height: int) -> CoverPlacement:
    foreground = _foreground_cover(cover.convert("RGBA"), width, height)
    layout = plan_wallpaper_layout(
        cover,
        title="Ag",
        artist="Ag",
        width=width,
        height=height,
    )
    x0, y0, x1, y1 = layout.cover
    corner_radius = max(12, min(foreground.width, foreground.height) // COVER_CORNER_RADIUS_DIVISOR)
    return CoverPlacement(
        x=x0,
        y=y0,
        width=x1 - x0,
        height=y1 - y0,
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
    *,
    highlight_alpha: int | None = None,
) -> Image.Image:
    layer = canvas.convert("RGBA")
    draw = ImageDraw.Draw(layer)
    inset = _rim_highlight_width(screen_height) // 2
    alpha = RIM_HIGHLIGHT_ALPHA if highlight_alpha is None else highlight_alpha
    draw.rounded_rectangle(
        (
            placement.x + inset,
            placement.y + inset,
            placement.x + placement.width - inset - 1,
            placement.y + placement.height - inset - 1,
        ),
        radius=max(1, placement.corner_radius - inset),
        outline=(255, 255, 255, alpha),
        width=_rim_highlight_width(screen_height),
    )
    return layer


def _render_text_layer_supersampled(
    text: str,
    *,
    font_size: int,
    bold: bool,
    fill_alpha: int,
    canvas_width: int,
    fill_rgb: tuple[int, int, int] = (255, 255, 255),
    draw_shadow: bool = True,
) -> Image.Image:
    scale = TEXT_SUPERSAMPLE_FACTOR
    font = _load_font(font_size * scale, bold=bold)
    bbox = _text_bbox(text, font, anchor="mt")
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    pad = scale * 4
    layer_w = min(canvas_width * scale, text_w + pad * 2)
    layer_h = text_h + pad * 2
    layer = Image.new("RGBA", (layer_w, layer_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    cx = layer_w // 2
    top = pad - bbox[1]
    if draw_shadow:
        shadow_y = top + scale * 3
        draw.text(
            (cx, shadow_y),
            text,
            font=font,
            fill=(0, 0, 0, min(255, fill_alpha + 40)),
            anchor="mt",
        )
    draw.text(
        (cx, top),
        text,
        font=font,
        fill=(*fill_rgb, fill_alpha),
        anchor="mt",
    )
    down_w = max(1, layer_w // scale)
    down_h = max(1, layer_h // scale)
    return layer.resize((down_w, down_h), Image.Resampling.LANCZOS)


def _cover_shadow_clip_rect(
    placement: CoverPlacement,
    layout: WallpaperLayout,
    screen_height: int,
) -> tuple[int, int, int, int]:
    """Keep cover shadows under the artwork, not over the title block."""
    px0, py0, px1, py1 = layout.panel
    bleed = max(
        8,
        int(placement.height * COVER_SHADOW_AMBIENT_BLUR_FRAC * 0.45),
    )
    shadow_extent = max(
        int(placement.height * COVER_SHADOW_CONTACT_OFFSET_Y_FRAC),
        int(placement.height * COVER_SHADOW_AMBIENT_OFFSET_Y_FRAC),
    )
    max_shadow_y = placement.y + placement.height + shadow_extent + bleed
    text_top = layout.title[1] - max(4, screen_height // 80)
    y1_clip = min(max_shadow_y, text_top, py1)
    pad_x = int(placement.height * COVER_SHADOW_AMBIENT_PAD_FRAC)
    x0 = max(px0, placement.x - pad_x)
    x1 = min(px1, placement.x + placement.width + pad_x)
    y0 = max(py0, placement.y - bleed)
    return (x0, y0, x1, y1_clip)


def _clip_layer_to_rounded_rect(
    layer: Image.Image,
    rect: tuple[int, int, int, int],
    *,
    radius: int,
) -> Image.Image:
    x0, y0, x1, y1 = rect
    panel_mask = Image.new("L", layer.size, 0)
    draw = ImageDraw.Draw(panel_mask)
    draw.rounded_rectangle((x0, y0, x1 - 1, y1 - 1), radius=radius, fill=255)
    rgba = layer.convert("RGBA")
    red, green, blue, alpha = rgba.split()
    clipped = ImageChops.multiply(alpha, panel_mask)
    return Image.merge("RGBA", (red, green, blue, clipped))


def _apply_rounded_alpha(image: Image.Image, mask: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    red, green, blue, alpha = rgba.split()
    clipped = ImageChops.multiply(alpha, mask)
    return Image.merge("RGBA", (red, green, blue, clipped))


def _build_glass_panel_layer(
    backdrop: Image.Image,
    panel_rect: tuple[int, int, int, int],
    screen_height: int,
    *,
    adaptation: GlassContrastAdaptation | None = None,
) -> Image.Image:
    x0, y0, x1, y1 = panel_rect
    pw, ph = x1 - x0, y1 - y0
    radius = _glass_corner_radius(pw, ph)
    mask = _rounded_rectangle_mask((pw, ph), radius)
    crop = backdrop.crop(panel_rect).convert("RGBA")
    if adaptation is None:
        adaptation = _glass_contrast_adaptation(mean_luminance(backdrop, panel_rect))
    extra_blur = max(6.0, min(pw, ph) / GLASS_BACKDROP_EXTRA_BLUR_DIVISOR)
    crop = crop.filter(ImageFilter.GaussianBlur(radius=extra_blur))
    crop = ImageEnhance.Color(crop).enhance(GLASS_SATURATION_BOOST)
    tint = Image.new("RGBA", (pw, ph), (*adaptation.tint_rgb, adaptation.tint_alpha))
    glass = Image.alpha_composite(crop, tint)
    if adaptation.fill_lift_alpha > 0:
        lift = Image.new("RGBA", (pw, ph), (255, 255, 255, adaptation.fill_lift_alpha))
        glass = Image.alpha_composite(glass, lift)

    border_w = _scale_for_height(
        screen_height,
        GLASS_INNER_BORDER_SCREEN_HEIGHT_REF,
        GLASS_INNER_BORDER_WIDTH_REF,
    )
    inset = border_w
    border_layer = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
    draw = ImageDraw.Draw(border_layer)
    draw.rounded_rectangle(
        (inset, inset, pw - inset - 1, ph - inset - 1),
        radius=max(1, radius - inset),
        outline=(255, 255, 255, adaptation.inner_border_alpha),
        width=border_w,
    )
    glass = Image.alpha_composite(glass, border_layer)

    spec_h = max(8, int(ph * GLASS_SPECULAR_HEIGHT_FRAC))
    spec_layer = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
    spec_draw = ImageDraw.Draw(spec_layer)
    for row in range(spec_h):
        alpha = int(adaptation.specular_top_alpha * (1 - row / spec_h) ** 1.6)
        spec_draw.line([(0, row), (pw, row)], fill=(255, 255, 255, alpha))
    spec_layer = _apply_rounded_alpha(spec_layer, mask)
    glass = Image.alpha_composite(glass, spec_layer)
    return _apply_rounded_alpha(glass, mask)


def _trim_layer_alpha_above_y(layer: Image.Image, max_y: int) -> Image.Image:
    """Drop shadow pixels above ``max_y`` so the panel does not look doubled."""
    if max_y <= 0:
        return layer
    rgba = layer.convert("RGBA")
    w, h = rgba.size
    if max_y >= h:
        return layer
    red, green, blue, alpha = rgba.split()
    keep = alpha.crop((0, max_y, w, h))
    trimmed = Image.new("L", (w, h), 0)
    trimmed.paste(keep, (0, max_y))
    return Image.merge("RGBA", (red, green, blue, trimmed))


def _build_panel_drop_shadow(
    panel_rect: tuple[int, int, int, int],
    canvas_size: tuple[int, int],
    screen_height: int,
) -> Image.Image:
    x0, y0, x1, y1 = panel_rect
    pw, ph = x1 - x0, y1 - y0
    short = min(pw, ph)
    blur = max(10.0, short * GLASS_DROP_SHADOW_BLUR_FRAC)
    offset_y = max(2, int(short * GLASS_DROP_SHADOW_OFFSET_FRAC))
    shadow_w = max(48, int(pw * 0.86))
    shadow_h = max(16, int(ph * 0.14))
    shadow_radius = max(8, int(_glass_corner_radius(pw, ph) * 0.8))
    shadow_mask = _rounded_rectangle_mask((shadow_w, shadow_h), shadow_radius)
    shadow_fill = Image.new("RGBA", (shadow_w, shadow_h), (0, 0, 0, GLASS_DROP_SHADOW_ALPHA))
    shadow_fill = _apply_rounded_alpha(shadow_fill, shadow_mask)
    pad = max(4, int(blur * 2.5))
    padded = Image.new(
        "RGBA",
        (shadow_w + pad * 2, shadow_h + pad * 2),
        (0, 0, 0, 0),
    )
    padded.paste(shadow_fill, (pad, pad), shadow_fill)
    shadow_blur = padded.filter(ImageFilter.GaussianBlur(radius=blur))
    layer = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    paste_x = x0 + (pw - shadow_w) // 2 - pad
    paste_y = y1 + offset_y - pad
    layer.paste(shadow_blur, (paste_x, paste_y), shadow_blur)
    bleed_under = max(2, int(short * 0.006))
    return _trim_layer_alpha_above_y(layer, y1 + bleed_under)


def compose_wallpaper(
    cover: Image.Image,
    *,
    title: str,
    artist: str,
    width: int,
    height: int,
) -> Image.Image:
    """Build a wallpaper image at ``width`` x ``height``."""
    if width <= 0 or height <= 0:
        raise ValueError(f"Wallpaper size must be positive, got {width}x{height}")
    backdrop_rgb = render_backdrop(cover, width, height)
    canvas = backdrop_rgb.convert("RGBA")
    layout_spec = plan_wallpaper_layout(
        cover,
        title=title,
        artist=artist,
        width=width,
        height=height,
    )
    placement = compute_cover_placement(cover, width, height)
    layout = compute_text_layout(
        title=title,
        artist=artist,
        screen_width=width,
        screen_height=height,
        foreground_width=placement.width,
    )
    panel_rect = layout_spec.panel
    panel_adaptation = _glass_contrast_adaptation(mean_luminance(backdrop_rgb, panel_rect))
    mask = _rounded_rectangle_mask((placement.width, placement.height), placement.corner_radius)

    panel_radius = _glass_corner_radius(
        panel_rect[2] - panel_rect[0],
        panel_rect[3] - panel_rect[1],
    )
    canvas = Image.alpha_composite(
        canvas,
        _build_panel_drop_shadow(panel_rect, (width, height), height),
    )

    glow_color = extract_dominant_glow_color(cover)
    canvas = Image.alpha_composite(
        canvas,
        _clip_layer_to_rounded_rect(
            _build_glow_layer(glow_color, placement, (width, height)),
            panel_rect,
            radius=panel_radius,
        ),
    )
    cover_shadow_clip = _cover_shadow_clip_rect(placement, layout_spec, height)
    cover_shadow_layer = _build_layered_shadow_layer(placement, (width, height))
    cover_shadow_layer = _clip_layer_to_rounded_rect(
        cover_shadow_layer,
        cover_shadow_clip,
        radius=placement.corner_radius,
    )
    cover_shadow_layer = _clip_layer_to_rounded_rect(
        cover_shadow_layer,
        panel_rect,
        radius=panel_radius,
    )
    canvas = Image.alpha_composite(canvas, cover_shadow_layer)

    glass = _build_glass_panel_layer(
        backdrop_rgb,
        layout_spec.panel,
        height,
        adaptation=panel_adaptation,
    )
    px, py = layout_spec.panel[0], layout_spec.panel[1]
    glass_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    glass_layer.paste(glass, (px, py), glass)
    canvas = Image.alpha_composite(canvas, glass_layer)

    fg_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    fg_layer.paste(
        _foreground_cover(cover.convert("RGBA"), width, height),
        (placement.x, placement.y),
        mask,
    )
    canvas = Image.alpha_composite(canvas, fg_layer)
    canvas = _draw_rim_highlight(
        canvas,
        placement,
        height,
        highlight_alpha=panel_adaptation.rim_highlight_alpha,
    )

    title_layer = _render_text_layer_supersampled(
        layout.title,
        font_size=layout.title_font_size,
        bold=True,
        fill_alpha=255,
        canvas_width=width,
    )
    artist_layer = _render_text_layer_supersampled(
        layout.artist,
        font_size=layout.artist_font_size,
        bold=False,
        fill_alpha=ARTIST_TEXT_ALPHA,
        canvas_width=width,
        fill_rgb=ARTIST_TEXT_RGB,
        draw_shadow=False,
    )
    text_center_x = (layout_spec.title[0] + layout_spec.title[2]) // 2
    title_top = layout_spec.title[1]
    artist_top = layout_spec.artist[1]
    canvas = Image.alpha_composite(
        canvas,
        _paste_text_layer(title_layer, text_center_x, title_top, (width, height)),
    )
    canvas = Image.alpha_composite(
        canvas,
        _paste_text_layer(artist_layer, text_center_x, artist_top, (width, height)),
    )
    return canvas.convert("RGB")


def _paste_text_layer(
    layer: Image.Image,
    center_x: int,
    ink_top_y: int,
    canvas_size: tuple[int, int],
) -> Image.Image:
    out = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    alpha = layer.split()[3]
    ink_bbox = alpha.getbbox()
    ink_offset_y = ink_bbox[1] if ink_bbox else 0
    x = center_x - layer.width // 2
    y = ink_top_y - ink_offset_y
    out.paste(layer, (x, y), layer)
    return out


def save_wallpaper(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() in {".jpg", ".jpeg"}:
        image.save(path, format="JPEG", quality=95, optimize=True)
    else:
        image.save(path, format="PNG", optimize=True)
