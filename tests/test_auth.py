from unittest.mock import patch

from now_playing_desktops.auth import prompt_for_token


def test_prompt_for_token_missing_env(monkeypatch):
    monkeypatch.delenv("SPOTIPY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPOTIPY_CLIENT_SECRET", raising=False)
    assert prompt_for_token("user") is None


def test_prompt_for_token_uses_env(monkeypatch):
    monkeypatch.setenv("SPOTIPY_CLIENT_ID", "id")
    monkeypatch.setenv("SPOTIPY_CLIENT_SECRET", "secret")
    monkeypatch.setenv("SPOTIPY_REDIRECT_URI", "http://localhost/")

    with patch("now_playing_desktops.auth.util.prompt_for_user_token", return_value="tok") as mock:
        assert prompt_for_token("user") == "tok"
        mock.assert_called_once_with(
            "user",
            "user-read-currently-playing",
            client_id="id",
            client_secret="secret",
            redirect_uri="http://localhost/",
        )
