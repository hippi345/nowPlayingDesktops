from __future__ import annotations

import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from now_playing_desktops.composer import compose_wallpaper, plan_wallpaper_layout, save_wallpaper
from now_playing_desktops.verification.wallpaper_analysis import (
    assert_tile_centered,
    assert_tile_fully_visible,
    tile_centering_from_layout,
)
from tests.helpers import ARTIFACTS_DIR, make_sample_cover

LONG_TITLE = "Long Title For Centering"


@pytest.mark.parametrize(
    ("width", "height", "artifact_name"),
    [
        (1664, 1109, "linux-desktop-1664x1109.png"),
        (1920, 1080, None),
        (2560, 1440, None),
    ],
)
def test_linux_xvfb_desktop_centering_after_feh(
    tmp_path: Path,
    width: int,
    height: int,
    artifact_name: str | None,
):
    if not shutil.which("feh") or not shutil.which("xvfb-run"):
        pytest.skip("feh or xvfb-run missing")
    try:
        import mss  # noqa: F401
    except ImportError:
        pytest.skip("mss not installed")

    cover = make_sample_cover()
    layout = plan_wallpaper_layout(
        cover,
        title=LONG_TITLE,
        artist="Test Artist",
        width=width,
        height=height,
    )
    centering = tile_centering_from_layout(layout, screen_width=width, screen_height=height)
    assert_tile_centered(centering, tolerance_px=3.0)
    assert_tile_fully_visible(layout, screen_width=width, screen_height=height)

    image_path = tmp_path / f"wall-{width}x{height}.png"
    composed = compose_wallpaper(
        cover,
        title=LONG_TITLE,
        artist="Test Artist",
        width=width,
        height=height,
    )
    save_wallpaper(composed, image_path)

    script = textwrap.dedent(
        f"""
        import time
        import subprocess
        from pathlib import Path
        from PIL import Image
        import mss

        image = Path({str(image_path)!r})
        subprocess.run(["feh", "--bg-fill", str(image)], check=True)
        time.sleep(0.6)
        with mss.mss() as grabber:
            monitor = grabber.monitors[1]
            shot = grabber.grab(monitor)
            img = Image.frombytes("RGB", shot.size, shot.rgb)
            out = Path({str(tmp_path / "capture.png")!r})
            img.save(out)
        """
    )
    helper = tmp_path / "grab_desktop.py"
    helper.write_text(script, encoding="utf-8")
    subprocess.run(
        [
            "xvfb-run",
            "-a",
            "-s",
            f"-screen 0 {width}x{height}x24",
            sys.executable,
            str(helper),
        ],
        check=True,
        env=os.environ.copy(),
    )
    if artifact_name:
        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        capture_path = tmp_path / "capture.png"
        if capture_path.is_file():
            capture_path.replace(ARTIFACTS_DIR / artifact_name)
