from __future__ import annotations

from pathlib import Path

import pytest

from now_playing_desktops import env_loader
from now_playing_desktops.config import user_config_dir


def test_env_file_lookup_order(tmp_path: Path, monkeypatch):
    explicit = tmp_path / "explicit.env"
    from_var = tmp_path / "from-var.env"
    config_env = tmp_path / "config" / "now-playing-desktops" / ".env"
    cwd_env = tmp_path / "work" / ".env"

    explicit.write_text("SPOTIPY_CLIENT_ID=explicit\n", encoding="utf-8")
    from_var.write_text("SPOTIPY_CLIENT_ID=from_var\n", encoding="utf-8")
    config_env.parent.mkdir(parents=True)
    config_env.write_text("SPOTIPY_CLIENT_ID=config\n", encoding="utf-8")
    cwd_env.parent.mkdir(parents=True)
    cwd_env.write_text("SPOTIPY_CLIENT_ID=cwd\n", encoding="utf-8")

    monkeypatch.setenv("NOW_PLAYING_ENV_FILE", str(from_var))
    monkeypatch.setattr(env_loader, "user_config_dir", lambda: config_env.parent)
    monkeypatch.chdir(cwd_env.parent)

    assert env_loader.find_env_file(explicit=explicit) == explicit.resolve()
    assert env_loader.find_env_file() == from_var.resolve()

    monkeypatch.delenv("NOW_PLAYING_ENV_FILE", raising=False)
    assert env_loader.find_env_file() == config_env.resolve()

    monkeypatch.setattr(env_loader, "user_config_dir", lambda: tmp_path / "missing-config")
    assert env_loader.find_env_file() == cwd_env.resolve()


def test_load_environment_does_not_override_existing(tmp_path: Path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "SPOTIPY_CLIENT_ID=from_file\nSPOTIPY_CLIENT_SECRET=secret\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SPOTIPY_CLIENT_ID", "from_shell")
    monkeypatch.setattr(env_loader, "user_config_dir", lambda: tmp_path / "missing-config")
    monkeypatch.chdir(tmp_path)

    loaded = env_loader.load_environment(verbose=False)
    assert loaded == env_path.resolve()
    assert env_loader.spotify_credentials_configured() is True
    assert env_loader.merged_env_values()["SPOTIPY_CLIENT_ID"] == "from_shell"
    assert env_loader.merged_env_values()["SPOTIPY_CLIENT_SECRET"] == "secret"


def test_load_environment_logs_path_in_verbose_mode(tmp_path: Path, monkeypatch, caplog):
    env_path = tmp_path / ".env"
    env_path.write_text("SPOTIPY_CLIENT_ID=id\nSPOTIPY_CLIENT_SECRET=secret\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    with caplog.at_level("DEBUG"):
        env_loader.load_environment(verbose=True)

    assert str(env_path.resolve()) in caplog.text
    assert "secret" not in caplog.text


def test_missing_env_file_message_mentions_config_dir(monkeypatch):
    monkeypatch.setattr(env_loader, "user_config_dir", lambda: Path("/tmp/npd-config"))
    message = env_loader.missing_env_file_message()
    assert "/tmp/npd-config/.env" in message


def test_resolve_spotify_username_prefers_cli(monkeypatch):
    monkeypatch.setenv("SPOTIPY_CLIENT_USERNAME", "from_env")
    assert env_loader.resolve_spotify_username("cli_user") == "cli_user"


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ({}, False),
        ({"SPOTIPY_CLIENT_ID": "id"}, False),
        ({"SPOTIPY_CLIENT_ID": "id", "SPOTIPY_CLIENT_SECRET": "secret"}, True),
    ],
)
def test_spotify_credentials_configured(tmp_path: Path, monkeypatch, values, expected):
    env_path = tmp_path / ".env"
    lines = [f"{key}={value}\n" for key, value in values.items()]
    env_path.write_text("".join(lines), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(env_loader, "user_config_dir", lambda: tmp_path / "missing-config")
    monkeypatch.delenv("SPOTIPY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPOTIPY_CLIENT_SECRET", raising=False)
    assert env_loader.spotify_credentials_configured() is expected


def test_user_config_dir_default_name():
    path = user_config_dir()
    assert path.name == "now-playing-desktops"
