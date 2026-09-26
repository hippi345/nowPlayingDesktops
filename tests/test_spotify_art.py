from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from now_playing_desktops.spotify_art import (
    current_album_art_url,
    download_album_art,
    fetch_current_playback,
    pick_album_image_url,
    poll_and_update_wallpaper,
)


def test_pick_album_image_url_prefers_largest():
    images = [{"url": "large"}, {"url": "medium"}, {"url": "small"}]
    assert pick_album_image_url(images) == "large"


def test_pick_album_image_url_single_image():
    assert pick_album_image_url([{"url": "only"}]) == "only"


def test_pick_album_image_url_empty():
    assert pick_album_image_url([]) is None


def test_current_album_art_url_when_nothing_playing():
    sp = MagicMock()
    sp.current_user_playing_track.return_value = None
    assert current_album_art_url(sp) is None


def test_current_album_art_url_returns_largest_image():
    sp = MagicMock()
    sp.current_user_playing_track.return_value = {
        "is_playing": True,
        "item": {
            "id": "abc",
            "name": "Track",
            "artists": [{"name": "Band"}],
            "album": {"images": [{"url": "a"}, {"url": "b"}]},
        },
    }
    assert current_album_art_url(sp) == "a"


def test_fetch_current_playback_respects_is_playing_flag():
    sp = MagicMock()
    sp.current_user_playing_track.return_value = {
        "is_playing": False,
        "item": {
            "id": "abc",
            "name": "Track",
            "artists": [{"name": "Band"}],
            "album": {"images": [{"url": "a"}]},
        },
    }
    track = fetch_current_playback(sp)
    assert track is not None
    assert track.is_playing is False


def test_download_album_art_writes_file(tmp_path: Path):
    session = MagicMock()
    response = MagicMock()
    response.iter_content.return_value = [b"abc", b"def"]
    response.raise_for_status = MagicMock()
    session.get.return_value = response

    dest = tmp_path / "art.jpg"
    download_album_art("https://example.com/art.jpg", dest, session=session)

    assert dest.read_bytes() == b"abcdef"
    session.get.assert_called_once_with("https://example.com/art.jpg", stream=True, timeout=30)


def test_poll_and_update_wallpaper_invokes_callbacks_when_playing(tmp_path: Path):
    sp = MagicMock()
    sp.current_user_playing_track.return_value = {
        "is_playing": True,
        "item": {
            "id": "x",
            "name": "n",
            "artists": [{"name": "a"}],
            "album": {"images": [{"url": "x"}]},
        },
    }

    paths: list[Path] = []

    def prepare(_url: str) -> Path:
        path = tmp_path / "wall.jpg"
        paths.append(path)
        return path

    set_calls: list[Path] = []

    def set_wallpaper(path: Path) -> None:
        set_calls.append(path)

    with (
        patch(
            "now_playing_desktops.spotify_art.download_album_art",
            side_effect=lambda url, dest, session=None: dest.write_bytes(b"1"),
        ),
        patch(
            "now_playing_desktops.spotify_art.time.sleep",
            side_effect=KeyboardInterrupt,
        ),
        pytest.raises(KeyboardInterrupt),
    ):
        poll_and_update_wallpaper(
            sp,
            poll_interval_seconds=0,
            prepare_artwork=prepare,
            set_wallpaper=set_wallpaper,
        )

    assert set_calls == paths


def test_poll_and_update_wallpaper_skips_when_no_track():
    sp = MagicMock()
    sp.current_user_playing_track.return_value = None

    with (
        patch("now_playing_desktops.spotify_art.time.sleep", side_effect=KeyboardInterrupt),
        pytest.raises(KeyboardInterrupt),
    ):
        poll_and_update_wallpaper(
            sp,
            poll_interval_seconds=0,
            prepare_artwork=lambda _u: Path("/unused"),
            set_wallpaper=lambda _p: None,
        )
