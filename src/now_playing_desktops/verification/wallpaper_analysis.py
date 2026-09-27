"""Analyze composed wallpapers and desktop captures for layout regressions."""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageChops, ImageStat

from now_playing_desktops.composer import WallpaperLayout, mean_luminance, render_backdrop


@dataclass(frozen=True)
class TileCenteringResult:
    screen_width: int
    screen_height: int
    tile_center_x: float
    tile_center_y: float
    offset_x: float
    offset_y: float


@dataclass(frozen=True)
class BandEdgeFinding:
    orientation: str
    index: int
    strength: float
    span_fraction: float


def _image_variance(image: Image.Image) -> float:
    stat = ImageStat.Stat(image)
    return float(sum(v for v in stat.var))


def tile_centering_from_layout(
    layout: WallpaperLayout,
    *,
    screen_width: int,
    screen_height: int,
) -> TileCenteringResult:
    px0, py0, px1, py1 = layout.panel
    cx = (px0 + px1) / 2.0
    cy = (py0 + py1) / 2.0
    return TileCenteringResult(
        screen_width=screen_width,
        screen_height=screen_height,
        tile_center_x=cx,
        tile_center_y=cy,
        offset_x=cx - screen_width / 2.0,
        offset_y=cy - screen_height / 2.0,
    )


def assert_tile_centered(
    result: TileCenteringResult,
    *,
    tolerance_px: float = 4.0,
) -> None:
    if abs(result.offset_x) > tolerance_px or abs(result.offset_y) > tolerance_px:
        raise AssertionError(
            f"Tile center ({result.tile_center_x:.1f}, {result.tile_center_y:.1f}) "
            f"off screen center by ({result.offset_x:.1f}, {result.offset_y:.1f}) px "
            f"(tolerance {tolerance_px})",
        )


def assert_tile_fully_visible(
    layout: WallpaperLayout,
    *,
    screen_width: int,
    screen_height: int,
    margin_px: int = 2,
) -> None:
    px0, py0, px1, py1 = layout.panel
    if px0 < margin_px or py0 < margin_px:
        raise AssertionError(f"Tile panel clipped at top/left: {(px0, py0, px1, py1)}")
    if px1 > screen_width - margin_px or py1 > screen_height - margin_px:
        raise AssertionError(f"Tile panel clipped at bottom/right: {(px0, py0, px1, py1)}")


def assert_glass_panel_present(
    composed: Image.Image,
    layout: WallpaperLayout,
    backdrop: Image.Image,
    *,
    min_luminance_delta: float = 4.0,
    min_uniformity_gain: float = 0.08,
    require_uniformity: bool = True,
) -> None:
    px0, py0, px1, py1 = layout.panel
    cx0, cy0, cx1, cy1 = layout.cover
    ring_boxes = [
        (px0 + 4, py0 + 4, cx0 - 2, cy1 - 2),
        (cx1 + 2, py0 + 4, px1 - 4, cy1 - 2),
    ]
    panel_lums: list[float] = []
    backdrop_lums: list[float] = []
    for box in ring_boxes:
        if box[2] <= box[0] or box[3] <= box[1]:
            continue
        panel_lums.append(mean_luminance(composed, box))
        backdrop_lums.append(mean_luminance(backdrop, box))
    if not panel_lums:
        raise AssertionError("Could not sample glass ring around cover")
    panel_mean = sum(panel_lums) / len(panel_lums)
    backdrop_mean = sum(backdrop_lums) / len(backdrop_lums)
    if abs(panel_mean - backdrop_mean) < min_luminance_delta:
        raise AssertionError(
            f"Glass ring not distinct from backdrop "
            f"(panel={panel_mean:.2f}, backdrop={backdrop_mean:.2f})",
        )

    inner = composed.crop((cx0 + 2, cy0 + 2, cx1 - 2, cy1 - 2)).convert("L")
    outer = composed.crop((px0 + 6, py0 + 6, px1 - 6, py1 - 6)).convert("L")
    inner_var = _image_variance(inner)
    outer_var = _image_variance(outer)
    if require_uniformity and inner_var > 0 and outer_var / inner_var < 1.0 + min_uniformity_gain:
        raise AssertionError(
            f"Glass panel lacks frosted uniformity (inner_var={inner_var:.1f}, "
            f"outer_var={outer_var:.1f})",
        )


def glass_ring_luminance_means(
    composed: Image.Image,
    layout: WallpaperLayout,
    backdrop: Image.Image,
) -> tuple[float, float]:
    """Return mean luminance of the glass ring samples and matching backdrop samples."""
    px0, py0, px1, py1 = layout.panel
    cx0, cy0, cx1, cy1 = layout.cover
    ring_boxes = [
        (px0 + 4, py0 + 4, cx0 - 2, cy1 - 2),
        (cx1 + 2, py0 + 4, px1 - 4, cy1 - 2),
    ]
    panel_lums: list[float] = []
    backdrop_lums: list[float] = []
    for box in ring_boxes:
        if box[2] <= box[0] or box[3] <= box[1]:
            continue
        panel_lums.append(mean_luminance(composed, box))
        backdrop_lums.append(mean_luminance(backdrop, box))
    if not panel_lums:
        return 0.0, 0.0
    return sum(panel_lums) / len(panel_lums), sum(backdrop_lums) / len(backdrop_lums)


def glass_ring_luminance_margin(
    composed: Image.Image,
    layout: WallpaperLayout,
    backdrop: Image.Image,
) -> float:
    panel_mean, backdrop_mean = glass_ring_luminance_means(composed, layout, backdrop)
    return abs(panel_mean - backdrop_mean)


def assert_title_text_present(
    composed: Image.Image,
    layout: WallpaperLayout,
    *,
    min_bright_pixels: int = 40,
) -> None:
    tx0, ty0, tx1, ty1 = layout.title
    ax0, ay0, ax1, ay1 = layout.artist
    title_band = composed.crop((tx0 - 20, ty0 - 4, tx1 + 20, ty1 + 8))
    artist_band = composed.crop((ax0 - 20, ay0 - 4, ax1 + 20, ay1 + 8))
    title_bright = sum(1 for rgb in title_band.getdata() if rgb[0] >= 200)
    artist_bright = sum(1 for rgb in artist_band.getdata() if rgb[0] >= 170)
    if title_bright < min_bright_pixels:
        raise AssertionError(f"Title text missing in render (bright pixels={title_bright})")
    if artist_bright < min_bright_pixels // 2:
        raise AssertionError(f"Artist text missing in render (bright pixels={artist_bright})")


def _difference_gray(composed: Image.Image, backdrop: Image.Image) -> Image.Image:
    diff = ImageChops.difference(composed.convert("RGB"), backdrop.convert("RGB"))
    return diff.convert("L")


def find_backdrop_band_edges(
    composed: Image.Image,
    backdrop: Image.Image,
    *,
    min_span_fraction: float = 0.22,
    gradient_threshold: float = 7.5,
    max_findings: int = 8,
) -> list[BandEdgeFinding]:
    """Detect long straight discontinuities between composed and pure backdrop."""
    diff = _difference_gray(composed, backdrop)
    width, height = diff.size
    pixels = diff.load()
    findings: list[BandEdgeFinding] = []

    for y in range(height - 1):
        strong = 0
        row_max = 0
        for x in range(width):
            delta = abs(int(pixels[x, y + 1]) - int(pixels[x, y]))
            row_max = max(row_max, delta)
            if delta > gradient_threshold:
                strong += 1
        if strong >= int(width * min_span_fraction):
            findings.append(
                BandEdgeFinding(
                    orientation="horizontal",
                    index=y,
                    strength=float(row_max),
                    span_fraction=strong / width,
                ),
            )

    for x in range(width - 1):
        strong = 0
        col_max = 0
        for y in range(height):
            delta = abs(int(pixels[x + 1, y]) - int(pixels[x, y]))
            col_max = max(col_max, delta)
            if delta > gradient_threshold:
                strong += 1
        if strong >= int(height * min_span_fraction):
            findings.append(
                BandEdgeFinding(
                    orientation="vertical",
                    index=x,
                    strength=float(col_max),
                    span_fraction=strong / height,
                ),
            )

    findings.sort(key=lambda item: item.strength, reverse=True)
    return findings[:max_findings]


def assert_no_backdrop_band_edges(
    composed: Image.Image,
    cover: Image.Image,
    *,
    exclude_panel_margin: int = 48,
    layout: WallpaperLayout | None = None,
    min_span_fraction: float = 0.22,
    gradient_threshold: float = 7.5,
    max_findings: int = 8,
) -> None:
    backdrop = render_backdrop(cover, composed.width, composed.height)
    findings = find_backdrop_band_edges(
        composed,
        backdrop,
        min_span_fraction=min_span_fraction,
        gradient_threshold=gradient_threshold,
        max_findings=max_findings,
    )
    if layout is None:
        if findings:
            first = findings[0]
            raise AssertionError(
                f"Backdrop band edge detected ({first.orientation} at {first.index}, "
                f"strength={first.strength:.1f})",
            )
        return

    px0, py0, px1, py1 = layout.panel
    ex0 = max(0, px0 - exclude_panel_margin)
    ey0 = max(0, py0 - exclude_panel_margin)
    ex1 = min(composed.width, px1 + exclude_panel_margin)
    ey1 = min(composed.height, py1 + exclude_panel_margin)
    for finding in findings:
        if finding.orientation == "horizontal":
            y = finding.index
            if ey0 <= y <= ey1:
                continue
        else:
            x = finding.index
            if ex0 <= x <= ex1:
                continue
        raise AssertionError(
            f"Backdrop band edge outside panel ({finding.orientation} at "
            f"{finding.index}, strength={finding.strength:.1f}, "
            f"span={finding.span_fraction:.2f})",
        )


def panel_bbox_from_capture(
    capture: Image.Image,
    *,
    backdrop: Image.Image,
    search_margin: int = 80,
) -> tuple[int, int, int, int]:
    """Estimate the frosted panel bounding box on a desktop capture."""
    if capture.size != backdrop.size:
        backdrop = backdrop.resize(capture.size, Image.Resampling.BILINEAR)
    diff = _difference_gray(capture, backdrop)
    width, height = diff.size
    cy, cx = height // 2, width // 2
    y0 = max(0, cy - search_margin * 3)
    y1 = min(height, cy + search_margin * 3)
    x0 = max(0, cx - search_margin * 3)
    x1 = min(width, cx + search_margin * 3)
    region = diff.crop((x0, y0, x1, y1))
    stat = ImageStat.Stat(region)
    threshold = stat.mean[0] + stat.stddev[0] * 0.35
    mask = region.point(lambda value: 255 if value > threshold else 0)
    bbox = mask.getbbox()
    if bbox is None:
        raise AssertionError("Could not locate tile region in desktop capture")
    rx0, ry0, rx1, ry1 = bbox
    return (x0 + rx0, y0 + ry0, x0 + rx1, y0 + ry1)
