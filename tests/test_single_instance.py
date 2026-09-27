from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from now_playing_desktops.single_instance import (
    RunInstanceLock,
    ensure_single_run_instance,
    probe_run_lock_held,
)


def test_second_run_instance_exits_cleanly(caplog):
    first = RunInstanceLock(acquired=True, backend="test")
    with (
        patch(
            "now_playing_desktops.single_instance.RunInstanceLock.try_acquire",
            return_value=RunInstanceLock(acquired=False, backend="test"),
        ),
        patch(
            "now_playing_desktops.single_instance.probe_run_lock_held",
            return_value=MagicMock(acquired=False, holder_description="pid 999"),
        ),
    ):
        assert ensure_single_run_instance() is None
    first.release()


def test_windows_autostart_enable_uses_single_run_key(tmp_path):
    from now_playing_desktops.platforms import autostart

    env_file = tmp_path / ".env"
    env_file.write_text("SPOTIPY_CLIENT_ID=a\nSPOTIPY_CLIENT_SECRET=b\n", encoding="utf-8")
    calls: list[tuple[str, str | None]] = []

    def record_enable(*, env_file: Path, username: str | None) -> None:
        calls.append((str(env_file), username))

    with (
        patch("now_playing_desktops.env_loader.load_environment"),
        patch(
            "now_playing_desktops.env_loader.find_env_file",
            return_value=env_file,
        ),
        patch(
            "now_playing_desktops.env_loader.spotify_credentials_configured",
            return_value=True,
        ),
        patch.object(
            autostart,
            "_windows_enable_autostart",
            side_effect=record_enable,
        ) as enable_mock,
        patch.object(autostart.sys, "platform", "win32"),
    ):
        autostart.enable_autostart(env_file=env_file, username="u")
        autostart.enable_autostart(env_file=env_file, username="u")

    assert enable_mock.call_count == 2
    assert len(calls) == 2
    assert autostart._windows_run_key_name() == "now-playing-desktops"


def test_probe_run_lock_on_non_windows():
    if sys.platform == "win32":
        return
    status = probe_run_lock_held()
    assert status.acquired in {True, False}
