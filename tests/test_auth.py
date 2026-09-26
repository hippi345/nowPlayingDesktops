from unittest.mock import MagicMock, patch

from now_playing_desktops.auth import prompt_for_token


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
