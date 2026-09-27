from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

from now_playing_desktops.art_resolution import (
    artist_names_match,
    lookup_itunes_artwork_url,
    render_placeholder_cover,
    resolve_track_art,
)
from now_playing_desktops.cover_art import load_track_cover
from now_playing_desktops.playback_types import TrackPlayback
from now_playing_desktops.sources.local.windows_smtc_thumbnail import (
    read_random_access_stream_bytes,
    read_thumbnail_reference_bytes,
)


def _png_bytes(
    size: tuple[int, int] = (64, 64),
    color: tuple[int, int, int] = (20, 40, 80),
) -> bytes:
    image = Image.new("RGB", size, color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_artist_names_match_fuzzy():
    assert artist_names_match("Joyce Wrice", "Joyce Wrice")
    assert artist_names_match("The Beatles", "Beatles")
    assert not artist_names_match("Artist A", "Totally Different")


def test_resolve_track_art_keeps_small_smtc_without_blocking_itunes(tmp_path: Path):
    small = _png_bytes((300, 300))
    track = TrackPlayback("id", "", "Title", "Artist", True, art_bytes=small)
    session = MagicMock()
    resolved = resolve_track_art(track, download_dir=tmp_path, session=session)
    assert resolved.source == "smtc_thumbnail"
    assert resolved.width == 300
    session.get.assert_not_called()


def test_try_fetch_itunes_upgrade_when_larger(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("NOW_PLAYING_ONLINE_ART", raising=False)
    from now_playing_desktops.art_resolution import try_fetch_itunes_upgrade

    small = _png_bytes((300, 300))
    large = _png_bytes((1000, 1000), color=(200, 10, 10))
    track = TrackPlayback("id", "", "Title", "Artist", True, art_bytes=small)
    session = MagicMock()
    session.get.side_effect = [
        MagicMock(
            status_code=200,
            json=lambda: {
                "results": [{"artistName": "Artist", "artworkUrl100": "https://x/100x100bb.jpg"}]
            },
        ),
        MagicMock(status_code=200, content=large),
    ]
    upgraded = try_fetch_itunes_upgrade(
        track,
        smtc_max_dim=300,
        download_dir=tmp_path,
        session=session,
    )
    assert upgraded is not None
    assert upgraded.width == 1000


def test_resolve_track_art_keeps_large_smtc_without_itunes_call(tmp_path: Path):
    data = _png_bytes((800, 800))
    track = TrackPlayback("id", "", "Title", "Artist", True, art_bytes=data)
    session = MagicMock()
    resolved = resolve_track_art(track, download_dir=tmp_path, session=session)
    assert resolved.source == "smtc_thumbnail"
    session.get.assert_not_called()


def test_resolve_track_art_prefers_smtc_bytes(tmp_path: Path):
    data = _png_bytes((700, 700))
    track = TrackPlayback("id", "", "Title", "Artist", True, art_bytes=data)
    resolved = resolve_track_art(track, download_dir=tmp_path)
    assert resolved.source == "smtc_thumbnail"
    assert resolved.image_bytes == data


def test_resolve_track_art_itunes_when_no_bytes(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("NOW_PLAYING_ONLINE_ART", raising=False)
    track = TrackPlayback("id", "", "Fly", "Joyce Wrice", True)
    session = MagicMock()
    session.get.side_effect = [
        MagicMock(
            status_code=200,
            json=lambda: {
                "results": [
                    {
                        "artistName": "Joyce Wrice",
                        "artworkUrl100": "https://example.com/100x100bb.jpg",
                    }
                ]
            },
        ),
        MagicMock(status_code=200, content=_png_bytes((300, 300))),
    ]
    resolved = resolve_track_art(track, download_dir=tmp_path, session=session)
    assert resolved.source == "itunes"
    assert resolved.width == 300


def test_resolve_track_art_placeholder_when_all_fail(tmp_path: Path):
    track = TrackPlayback("id", "", "Title", "Artist", True)
    session = MagicMock()
    session.get.side_effect = Exception("network down")
    resolved = resolve_track_art(track, download_dir=tmp_path, session=session)
    assert resolved.source == "placeholder"
    assert resolved.width == 1000


def test_load_track_cover_never_raises_without_art(tmp_path: Path, caplog):
    import logging

    track = TrackPlayback("id", "", "Title", "Artist", True)
    session = MagicMock()
    session.get.side_effect = Exception("offline")
    with caplog.at_level(logging.INFO):
        cover = load_track_cover(track, download_dir=tmp_path, session=session)
    assert cover.size[0] > 0
    assert "Track art source: placeholder" in caplog.text
    assert "Track thumbnail size:" in caplog.text


def test_read_thumbnail_reference_retries_empty(monkeypatch):
    import asyncio

    attempts = {"count": 0}

    class FakeStream:
        size = 0

    class FakeThumb:
        async def open_read_async(self):
            attempts["count"] += 1
            return FakeStream()

    monkeypatch.setattr(
        "now_playing_desktops.sources.local.windows_smtc_thumbnail._THUMBNAIL_RETRY_ATTEMPTS",
        3,
    )
    monkeypatch.setattr(
        "now_playing_desktops.sources.local.windows_smtc_thumbnail._THUMBNAIL_RETRY_DELAY_SECONDS",
        0,
    )

    async def _run():
        result = await read_thumbnail_reference_bytes(FakeThumb(), attempts=3, delay_seconds=0)
        assert result is None
        assert attempts["count"] == 3

    asyncio.run(_run())


def test_read_random_access_stream_bytes_reads_buffer(monkeypatch):
    import asyncio
    from unittest.mock import patch

    pytest.importorskip("winrt.windows.storage.streams")

    class FakeBuffer:
        def __init__(self, size):
            self.capacity = size
            self._data = bytearray(size)

        def __buffer__(self, flags):
            return memoryview(self._data)

    class FakeStream:
        size = 3

        async def read_async(self, buffer, count, _options):
            buffer._data[:count] = b"abc"[:count]
            return count

    async def passthrough(awaitable, **_kwargs):
        return await awaitable

    async def _run():
        with (
            patch("winrt.windows.storage.streams.Buffer", FakeBuffer),
            patch(
                "now_playing_desktops.sources.local.windows_smtc_thumbnail.winrt_wait",
                passthrough,
            ),
        ):
            data = await read_random_access_stream_bytes(FakeStream())
        assert data == b"abc"

    asyncio.run(_run())


def test_itunes_cache_hit(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("NOW_PLAYING_ONLINE_ART", raising=False)
    session = MagicMock()
    session.get.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "results": [
                {"artistName": "Artist", "artworkUrl100": "https://x/100x100bb.png"},
            ]
        },
    )
    first = lookup_itunes_artwork_url("Artist", "Song", session=session, cache_dir=tmp_path)
    assert first == "https://x/1000x1000bb.png"
    session.reset_mock()
    second = lookup_itunes_artwork_url("Artist", "Song", session=session, cache_dir=tmp_path)
    assert second == first
    session.get.assert_not_called()


def test_placeholder_cover_renders():
    image = render_placeholder_cover("Title", "Artist", size=400)
    assert image.size == (400, 400)
