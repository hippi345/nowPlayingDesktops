from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


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


ARTIFACTS_DIR = Path("/opt/cursor/artifacts")
