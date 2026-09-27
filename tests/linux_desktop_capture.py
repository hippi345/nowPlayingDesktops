"""Capture and analyze real Linux root-window screenshots (Xvfb + feh)."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

from PIL import Image, ImageChops

from tests.helpers import ARTIFACTS_DIR, image_variance

_DIFF_CENTER_THRESHOLD = 15

_MIN_CAPTURE_BYTES = 8_000
_UNIFORM_UNIQUE_SAMPLE_MAX = 4


def require_linux_capture_tools() -> None:
    missing = [name for name in ("Xvfb", "feh", "openbox") if shutil.which(name) is None]
    try:
        import mss  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("mss is required for Linux desktop capture tests") from exc
    if missing:
        raise RuntimeError(f"Missing Linux desktop tools: {', '.join(missing)}")


def start_xvfb(display: str, width: int, height: int) -> subprocess.Popen[bytes]:
    proc = subprocess.Popen(
        ["Xvfb", display, "-screen", "0", f"{width}x{height}x24", "-ac"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(0.5)
    if proc.poll() is not None:
        raise RuntimeError(f"Xvfb failed to start on {display}")
    return proc


def start_openbox(display: str, home: Path) -> subprocess.Popen[bytes]:
    env = {"DISPLAY": display, "HOME": str(home), "PATH": os.environ.get("PATH", "")}
    return subprocess.Popen(
        ["openbox"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )


def desktop_env(display: str, home: Path) -> dict[str, str]:
    return {
        "DISPLAY": display,
        "HOME": str(home),
        "PATH": os.environ.get("PATH", ""),
    }


def feh_set_wallpaper(image: Path, *, env: dict[str, str]) -> None:
    subprocess.run(
        ["feh", "--bg-fill", str(image.resolve())],
        check=True,
        env=env,
        timeout=30,
    )


def capture_root_png(display: str, output: Path) -> Image.Image:
    import mss

    with mss.MSS(display=display) as grabber:
        monitor = grabber.monitors[1]
        shot = grabber.grab(monitor)
    image = Image.frombytes("RGB", shot.size, shot.rgb)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="PNG")
    return image


def mean_pixel_difference(left: Image.Image, right: Image.Image) -> float:
    if left.size != right.size:
        return 255.0
    diffs = [
        abs(channel_left - channel_right)
        for left_px, right_px in zip(
            left.convert("RGB").getdata(),
            right.convert("RGB").getdata(),
            strict=True,
        )
        for channel_left, channel_right in zip(left_px, right_px, strict=True)
    ]
    return sum(diffs) / len(diffs) if diffs else 0.0


def wait_for_non_uniform_capture(
    display: str,
    output: Path,
    *,
    timeout_seconds: float = 15.0,
    poll_seconds: float = 0.25,
    differ_from: Image.Image | None = None,
    min_difference: float = 18.0,
) -> Image.Image:
    deadline = time.monotonic() + timeout_seconds
    last: Image.Image | None = None
    while time.monotonic() < deadline:
        last = capture_root_png(display, output)
        if capture_is_blank(last, output):
            time.sleep(poll_seconds)
            continue
        if differ_from is not None and mean_pixel_difference(last, differ_from) < min_difference:
            time.sleep(poll_seconds)
            continue
        return last
    assert last is not None
    capture_is_blank(last, output, fail=True)
    if differ_from is not None:
        diff = mean_pixel_difference(last, differ_from)
        raise AssertionError(
            "root capture never changed from reference "
            f"(mean_diff={diff:.2f}, need>={min_difference})",
        )
    return last


def wait_for_capture_similar(
    display: str,
    output: Path,
    reference: Image.Image,
    *,
    timeout_seconds: float = 15.0,
    poll_seconds: float = 0.25,
    max_difference: float = 10.0,
) -> Image.Image:
    deadline = time.monotonic() + timeout_seconds
    last: Image.Image | None = None
    while time.monotonic() < deadline:
        last = capture_root_png(display, output)
        if capture_is_blank(last, output):
            time.sleep(poll_seconds)
            continue
        if mean_pixel_difference(last, reference) <= max_difference:
            return last
        time.sleep(poll_seconds)
    assert last is not None
    diff = mean_pixel_difference(last, reference)
    raise AssertionError(
        f"root capture did not return to reference wallpaper (mean_diff={diff:.2f})",
    )


def capture_is_blank(image: Image.Image, path: Path, *, fail: bool = False) -> bool:
    size_bytes = path.stat().st_size if path.is_file() else 0
    sample = list(image.getdata())[:: max(1, (image.size[0] * image.size[1]) // 5000)]
    unique = len({px for px in sample})
    blank = size_bytes < _MIN_CAPTURE_BYTES or unique <= _UNIFORM_UNIQUE_SAMPLE_MAX
    if blank and fail:
        raise AssertionError(
            f"root capture is blank or uniform (bytes={size_bytes}, unique_sample={unique})",
        )
    return blank


def tile_center_from_capture(
    image: Image.Image,
    *,
    differ_from: Image.Image | None = None,
) -> tuple[float, float]:
    """Locate the composed tile center from a root capture (not from composed PNG files)."""
    if differ_from is not None:
        if differ_from.size != image.size:
            raise AssertionError("baseline capture size does not match playing capture")
        return _tile_center_from_capture_diff(image, differ_from)
    width, height = image.size
    panel_w = max(32, int(width * 0.42))
    panel_h = max(32, int(height * 0.55))
    step_x = max(8, panel_w // 16)
    step_y = max(8, panel_h // 16)
    screen_cx = (width - 1) / 2
    screen_cy = (height - 1) / 2
    best_score = -1.0
    best_center = (screen_cx, screen_cy)
    for top in range(0, max(1, height - panel_h), step_y):
        for left in range(0, max(1, width - panel_w), step_x):
            box = (left, top, left + panel_w, top + panel_h)
            score = image_variance(image, box)
            dist = abs(left + panel_w / 2 - screen_cx) + abs(top + panel_h / 2 - screen_cy)
            score -= dist * 0.02
            if score <= best_score:
                continue
            best_score = score
            best_center = (left + panel_w / 2, top + panel_h / 2)
    if best_score <= 0:
        raise AssertionError("capture has no detectable tile (zero variance regions)")
    return best_center


def _tile_center_from_capture_diff(
    playing: Image.Image,
    baseline: Image.Image,
) -> tuple[float, float]:
    diff = ImageChops.difference(playing.convert("RGB"), baseline.convert("RGB"))
    mask = diff.convert("L").point(
        lambda value: 255 if value > _DIFF_CENTER_THRESHOLD else 0,
        mode="1",
    )
    bbox = mask.getbbox()
    if bbox is None:
        raise AssertionError("playing capture is identical to baseline (no tile visible)")
    left, top, right, bottom = bbox
    return ((left + right) / 2, (top + bottom) / 2)


def assert_tile_centered(
    image: Image.Image,
    *,
    differ_from: Image.Image | None = None,
    tolerance_px: float = 3.0,
) -> tuple[float, float]:
    width, height = image.size
    cx, cy = tile_center_from_capture(image, differ_from=differ_from)
    dx = abs(cx - (width - 1) / 2)
    dy = abs(cy - (height - 1) / 2)
    assert dx <= tolerance_px, f"horizontal center offset {dx:.2f}px > {tolerance_px}px"
    assert dy <= tolerance_px, f"vertical center offset {dy:.2f}px > {tolerance_px}px"
    return dx, dy


def captures_match(
    original: Image.Image, restored: Image.Image, *, tolerance: float = 10.0
) -> bool:
    return mean_pixel_difference(original, restored) <= tolerance


def save_linux_artifact(image: Image.Image, filename: str) -> Path:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    path = ARTIFACTS_DIR / filename
    image.save(path, format="PNG")
    return path
