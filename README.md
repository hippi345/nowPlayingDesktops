# nowPlayingDesktops

[![CI](https://github.com/hippi345/nowPlayingDesktops/actions/workflows/ci.yml/badge.svg)](https://github.com/hippi345/nowPlayingDesktops/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Set your desktop wallpaper to the album art of whatever you are playing on Spotify.

## Features

- **macOS (Spotify)** — updates the Finder desktop picture while a track is playing.
- **Windows (Spotify)** — updates the system wallpaper via the Windows API.
- Polls Spotify for the current track and refreshes artwork on an interval.
- OAuth via [Spotipy](https://github.com/spotipy-dev/spotipy); credentials stay in environment variables, not source code.

## Requirements

- Python **3.12+**
- A [Spotify Developer](https://developer.spotify.com/dashboard) application (Client ID and Client Secret)
- Spotify account with an active session while using the app
- **macOS**: `appscript` (installed automatically with the `macos` extra)
- **Windows**: runs on Windows with standard library `ctypes` (no extra packages)

## Setup

```bash
git clone https://github.com/hippi345/nowPlayingDesktops.git
cd nowPlayingDesktops
python3.12 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

On macOS, include the platform extra:

```bash
pip install -e ".[macos,dev]"
```

Copy the example environment file and fill in your Spotify app credentials:

```bash
cp .env.example .env
# Edit .env — never commit real secrets
export $(grep -v '^#' .env | xargs)   # or set variables in your shell profile
```

| Variable | Required | Description |
|----------|----------|-------------|
| `SPOTIPY_CLIENT_ID` | Yes | Spotify app Client ID |
| `SPOTIPY_CLIENT_SECRET` | Yes | Spotify app Client Secret |
| `SPOTIPY_REDIRECT_URI` | No | OAuth redirect (default `http://localhost/`) |

In the Spotify Developer Dashboard, add the redirect URI you use (for example `http://localhost/`) to your app settings.

## Usage

After exporting the environment variables, run the command for your platform (replace `your_spotify_username`):

**macOS**

```bash
now-playing-macos your_spotify_username
```

**Windows**

```bash
now-playing-windows your_spotify_username
```

On first run, Spotipy opens a browser flow to authorize the `user-read-currently-playing` scope. The process polls until you stop it with `Ctrl+C`.

### Legacy scripts

`macosSpotify.py` and `spotifyWindows.py` remain as thin wrappers around the package but are deprecated; prefer the console scripts above after `pip install`.

## Development

```bash
pip install -e ".[dev]"
ruff check src tests
ruff format src tests
pytest -q
python -m build
```

## Project structure

```
.github/workflows/ci.yml   # Lint, build, and test on push/PR
src/now_playing_desktops/  # Package: auth, Spotify helpers, platform wallpaper code
tests/                     # Offline unit tests (mocked Spotify/network)
macosSpotify.py            # Deprecated entry point
spotifyWindows.py          # Deprecated entry point
pyproject.toml             # Dependencies and tool configuration
```

## Roadmap

- macOS Apple Music
- Windows Apple Music
- Linux (if Spotify or Apple Music clients are available)

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 Joel Shearon.
