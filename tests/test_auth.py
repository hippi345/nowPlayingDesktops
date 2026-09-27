from unittest.mock import MagicMock, patch

from now_playing_desktops.auth import DEFAULT_REDIRECT_URI, prompt_for_token, spotify_oauth_manager


def test_default_redirect_uri_uses_loopback_callback():
    assert DEFAULT_REDIRECT_URI == "http://127.0.0.1:8765/callback"


def test_spotify_oauth_manager_uses_default_redirect_without_env(monkeypatch):
    monkeypatch.setenv("SPOTIPY_CLIENT_ID", "id")
    monkeypatch.setenv("SPOTIPY_CLIENT_SECRET", "secret")
    monkeypatch.delenv("SPOTIPY_REDIRECT_URI", raising=False)
    with patch("now_playing_desktops.auth.SpotifyOAuth") as oauth_mock:
        spotify_oauth_manager("user")
        oauth_mock.assert_called_once()
        assert oauth_mock.call_args.kwargs["redirect_uri"] == DEFAULT_REDIRECT_URI


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
    with patch("now_playing_desktops.auth.spotify_oauth_manager", return_value=manager):
        assert prompt_for_token("user") == "tok"
        manager.get_access_token.assert_called_once_with(as_dict=False)
