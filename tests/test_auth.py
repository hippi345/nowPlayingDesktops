import errno
import logging
from unittest.mock import MagicMock, patch

import pytest

from now_playing_desktops.auth import (
    DEFAULT_REDIRECT_URI,
    SCOPE,
    cache_handler_for_user,
    create_spotify_client,
    non_interactive_auth_message,
    port_in_use_message,
    prompt_for_token,
    spotify_auth_mode,
    spotify_oauth_manager,
    spotify_redirect_uri,
)


def test_default_redirect_uri_uses_loopback_callback():
    assert DEFAULT_REDIRECT_URI == "http://127.0.0.1:8897/callback"


def test_spotify_redirect_uri_falls_back_to_default(monkeypatch):
    monkeypatch.delenv("SPOTIPY_REDIRECT_URI", raising=False)
    assert spotify_redirect_uri() == DEFAULT_REDIRECT_URI


def test_spotify_redirect_uri_honors_override(monkeypatch):
    monkeypatch.setenv("SPOTIPY_REDIRECT_URI", "http://127.0.0.1:8898/callback")
    assert spotify_redirect_uri() == "http://127.0.0.1:8898/callback"


@pytest.mark.parametrize(
    ("secret", "expected"),
    [
        ("secret", "client_secret"),
        (None, "pkce"),
        ("", "pkce"),
        ("   ", "pkce"),
    ],
)
def test_spotify_auth_mode_selection(monkeypatch, secret, expected):
    monkeypatch.setenv("SPOTIPY_CLIENT_ID", "id")
    if secret is None:
        monkeypatch.delenv("SPOTIPY_CLIENT_SECRET", raising=False)
    else:
        monkeypatch.setenv("SPOTIPY_CLIENT_SECRET", secret)
    assert spotify_auth_mode() == expected


def test_spotify_oauth_manager_uses_client_secret_flow(monkeypatch, tmp_path):
    monkeypatch.setenv("SPOTIPY_CLIENT_ID", "id")
    monkeypatch.setenv("SPOTIPY_CLIENT_SECRET", "secret")
    monkeypatch.delenv("SPOTIPY_REDIRECT_URI", raising=False)
    monkeypatch.setattr(
        "now_playing_desktops.auth.user_config_dir",
        lambda: tmp_path,
    )
    with patch("now_playing_desktops.auth.SpotifyOAuth") as oauth_mock:
        spotify_oauth_manager("user")
        oauth_mock.assert_called_once()
        assert oauth_mock.call_args.kwargs["redirect_uri"] == DEFAULT_REDIRECT_URI
        assert "cache_handler" in oauth_mock.call_args.kwargs


def test_spotify_oauth_manager_uses_pkce_without_secret(monkeypatch, tmp_path):
    monkeypatch.setenv("SPOTIPY_CLIENT_ID", "id")
    monkeypatch.delenv("SPOTIPY_CLIENT_SECRET", raising=False)
    monkeypatch.setattr(
        "now_playing_desktops.auth.user_config_dir",
        lambda: tmp_path,
    )
    with patch("now_playing_desktops.auth.SpotifyPKCE") as pkce_mock:
        spotify_oauth_manager("user", interactive=True)
        pkce_mock.assert_called_once()
        assert pkce_mock.call_args.kwargs["open_browser"] is True


def test_token_cache_lives_under_user_config_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "now_playing_desktops.config.user_config_dir",
        lambda: tmp_path,
    )
    handler = cache_handler_for_user("myuser")
    assert handler.cache_path == str(tmp_path / "spotify-token-myuser.cache")


def test_prompt_for_token_missing_env(monkeypatch):
    monkeypatch.delenv("SPOTIPY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPOTIPY_CLIENT_SECRET", raising=False)
    assert prompt_for_token("user") is None


def test_prompt_for_token_uses_env(monkeypatch):
    monkeypatch.setenv("SPOTIPY_CLIENT_ID", "id")
    monkeypatch.setenv("SPOTIPY_CLIENT_SECRET", "secret")
    monkeypatch.setenv("SPOTIPY_REDIRECT_URI", "http://localhost/")

    manager = MagicMock()
    manager.get_access_token.return_value = "tok"
    with (
        patch("now_playing_desktops.auth.spotify_oauth_manager", return_value=manager),
        patch("now_playing_desktops.auth._precheck_oauth_redirect_port"),
    ):
        assert prompt_for_token("user") == "tok"
    manager.get_access_token.assert_called_once_with(as_dict=False)


@pytest.mark.parametrize(
    "bind_error",
    [
        PermissionError(13, "Access denied", None, 10013),
        OSError(errno.EADDRINUSE, "Address already in use"),
    ],
)
def test_oauth_bind_failure_exits_with_message(bind_error, monkeypatch, capsys):
    monkeypatch.setenv("SPOTIPY_CLIENT_ID", "id")
    monkeypatch.setenv("SPOTIPY_CLIENT_SECRET", "secret")
    monkeypatch.setenv("SPOTIPY_REDIRECT_URI", "http://127.0.0.1:8898/callback")

    manager = MagicMock()
    manager.redirect_uri = "http://127.0.0.1:8898/callback"
    manager.open_browser = True
    manager.cache_handler.get_cached_token.return_value = None
    manager.validate_token.return_value = None
    manager.get_access_token.side_effect = bind_error

    with (
        patch("now_playing_desktops.auth.spotify_oauth_manager", return_value=manager),
        patch("now_playing_desktops.auth.socket.socket") as socket_mock,
    ):
        sock = MagicMock()
        socket_mock.return_value = sock
        with pytest.raises(SystemExit) as exc:
            prompt_for_token("user")
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert err.strip() == port_in_use_message(8898)
    assert "Traceback" not in err


def test_precheck_uses_custom_redirect_port(monkeypatch):
    monkeypatch.setenv("SPOTIPY_CLIENT_ID", "id")
    monkeypatch.setenv("SPOTIPY_CLIENT_SECRET", "secret")
    monkeypatch.setenv("SPOTIPY_REDIRECT_URI", "http://127.0.0.1:8898/callback")

    manager = MagicMock()
    manager.redirect_uri = "http://127.0.0.1:8898/callback"
    manager.open_browser = True
    manager.cache_handler.get_cached_token.return_value = None
    manager.validate_token.return_value = None
    manager.get_access_token.return_value = "tok"

    with (
        patch("now_playing_desktops.auth.spotify_oauth_manager", return_value=manager),
        patch("now_playing_desktops.auth.socket.socket") as socket_mock,
    ):
        sock = MagicMock()
        socket_mock.return_value = sock
        assert prompt_for_token("user") == "tok"
        sock.bind.assert_called_once_with(("127.0.0.1", 8898))


def test_precheck_skipped_when_cached_token_valid(monkeypatch):
    monkeypatch.setenv("SPOTIPY_CLIENT_ID", "id")
    monkeypatch.setenv("SPOTIPY_CLIENT_SECRET", "secret")

    manager = MagicMock()
    manager.redirect_uri = DEFAULT_REDIRECT_URI
    manager.open_browser = True
    manager.cache_handler.get_cached_token.return_value = {"access_token": "cached"}
    manager.validate_token.return_value = {"access_token": "cached"}

    with (
        patch("now_playing_desktops.auth.spotify_oauth_manager", return_value=manager),
        patch("now_playing_desktops.auth.socket.socket") as socket_mock,
    ):
        assert create_spotify_client("user") is not None
        socket_mock.assert_not_called()


def test_precheck_bind_failure_before_oauth(monkeypatch, capsys):
    monkeypatch.setenv("SPOTIPY_CLIENT_ID", "id")
    monkeypatch.setenv("SPOTIPY_CLIENT_SECRET", "secret")
    monkeypatch.setenv("SPOTIPY_REDIRECT_URI", "http://127.0.0.1:8898/callback")

    manager = MagicMock()
    manager.redirect_uri = "http://127.0.0.1:8898/callback"
    manager.open_browser = True
    manager.cache_handler.get_cached_token.return_value = None
    manager.validate_token.return_value = None

    with (
        patch("now_playing_desktops.auth.spotify_oauth_manager", return_value=manager),
        patch("now_playing_desktops.auth.socket.socket") as socket_mock,
    ):
        sock = MagicMock()
        sock.bind.side_effect = OSError(errno.EADDRINUSE, "in use")
        socket_mock.return_value = sock
        with pytest.raises(SystemExit) as exc:
            prompt_for_token("user")
    assert exc.value.code == 1
    assert capsys.readouterr().err.strip() == port_in_use_message(8898)
    manager.get_access_token.assert_not_called()


def test_pkce_expired_token_refreshes_without_browser(monkeypatch):
    monkeypatch.setenv("SPOTIPY_CLIENT_ID", "id")
    monkeypatch.delenv("SPOTIPY_CLIENT_SECRET", raising=False)

    manager = MagicMock()
    manager.redirect_uri = DEFAULT_REDIRECT_URI
    manager.open_browser = False
    manager.cache_handler.get_cached_token.return_value = {
        "access_token": "old",
        "refresh_token": "rt",
        "scope": SCOPE,
    }
    manager.validate_token.return_value = {"access_token": "refreshed"}

    with (
        patch("now_playing_desktops.auth.spotify_oauth_manager", return_value=manager),
        patch("webbrowser.open") as browser_open,
    ):
        bundle = create_spotify_client("user")
    assert bundle is not None
    browser_open.assert_not_called()
    manager.get_access_token.assert_not_called()


def test_pkce_non_interactive_run_fails_without_cache(monkeypatch, caplog):
    monkeypatch.setenv("SPOTIPY_CLIENT_ID", "id")
    monkeypatch.delenv("SPOTIPY_CLIENT_SECRET", raising=False)

    manager = MagicMock()
    manager.cache_handler.get_cached_token.return_value = None
    manager.validate_token.return_value = None

    with (
        patch("now_playing_desktops.auth.spotify_oauth_manager", return_value=manager),
        patch("webbrowser.open") as browser_open,
        caplog.at_level(logging.ERROR),
    ):
        assert create_spotify_client("user") is None
    browser_open.assert_not_called()
    manager.get_access_token.assert_not_called()
    assert non_interactive_auth_message("user") in caplog.text


def test_auth_mode_logged_at_info(monkeypatch, caplog, tmp_path):
    monkeypatch.setenv("SPOTIPY_CLIENT_ID", "id")
    monkeypatch.delenv("SPOTIPY_CLIENT_SECRET", raising=False)
    monkeypatch.setattr(
        "now_playing_desktops.auth.user_config_dir",
        lambda: tmp_path,
    )
    with (
        patch("now_playing_desktops.auth.SpotifyPKCE"),
        caplog.at_level(logging.INFO),
    ):
        spotify_oauth_manager("user")
    assert "Spotify auth mode: pkce" in caplog.text
