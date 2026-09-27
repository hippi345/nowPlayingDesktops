"""Pytest hooks and shared fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_windows_com_probe_cache():
    """Prevent COM probe tests from leaving global availability cached for later tests."""
    from now_playing_desktops.platforms import windows_com as wc

    wc._com_available = None
    wc._com_probe_detail = ""
    wc._com_backend = None
    yield
    wc._com_available = None
    wc._com_probe_detail = ""
    wc._com_backend = None
