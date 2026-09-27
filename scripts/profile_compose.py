#!/usr/bin/env python3
"""Profile compose_wallpaper at 2496x1664 (laptop canvas)."""

from __future__ import annotations

import cProfile
import pstats
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from now_playing_desktops.composer import compose_wallpaper
from tests.helpers import make_sample_cover

CANVAS = (2496, 1664)


def main() -> None:
    cover = make_sample_cover(1000)
    compose_wallpaper(
        cover,
        title="River",
        artist="Cheat Codes",
        width=CANVAS[0],
        height=CANVAS[1],
    )
    started = time.perf_counter()
    profiler = cProfile.Profile()
    profiler.enable()
    compose_wallpaper(
        cover,
        title="River",
        artist="Cheat Codes",
        width=CANVAS[0],
        height=CANVAS[1],
    )
    profiler.disable()
    elapsed = time.perf_counter() - started
    print(f"compose_{CANVAS[0]}x{CANVAS[1]}_seconds={elapsed:.3f}")
    stats = pstats.Stats(profiler)
    stats.sort_stats("cumtime")
    stats.print_stats(20)


if __name__ == "__main__":
    main()
