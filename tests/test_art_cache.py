from pathlib import Path

from now_playing_desktops.art_cache import ComposedArtCache


def test_composed_art_cache_hit_returns_same_path(tmp_path: Path):
    cache = ComposedArtCache(tmp_path, max_entries=5)
    source = tmp_path / "source.png"
    source.write_bytes(b"png")
    first = cache.put("track", "https://art", 1920, 1080, source)
    hit = cache.get("track", "https://art", 1920, 1080)
    assert hit == first


def test_composed_art_cache_evicts_oldest_when_bounded(tmp_path: Path):
    cache = ComposedArtCache(tmp_path, max_entries=2)
    for index in range(3):
        src = tmp_path / f"{index}.png"
        src.write_bytes(str(index).encode())
        cache.put(f"t{index}", f"url{index}", 100, 100, src)
    remaining = list(tmp_path.glob("*.png"))
    assert len(remaining) == 2
