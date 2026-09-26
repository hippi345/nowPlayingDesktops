# nowPlayingDesktops

[![CI](https://github.com/hippi345/nowPlayingDesktops/actions/workflows/ci.yml/badge.svg)](https://github.com/hippi345/nowPlayingDesktops/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Set your desktop wallpaper to the album art of whatever you are playing on Spotify.

## Features

- **Windows** — multi-monitor aware sizing; optional per-monitor wallpaper when `IDesktopWallpaper` is available; `SystemParametersInfo` fallback.
- **macOS** — sets the wallpaper on **every** display (AppKit / `osascript`); per-screen restore.
- **Linux** — GNOME family (`gsettings`), KDE Plasma (`plasma-apply-wallpaperimage` / `qdbus`), and lightweight fallbacks (`feh`, `swaybg`, `nitrogen`) with full restore snapshots.
- Polls Spotify, composes a blurred backdrop + cover + track labels, and restores your original wallpaper on exit or pause.
- Login autostart: `now-playing autostart enable|disable|status` (Windows Run key, XDG `.desktop`, macOS LaunchAgent).

## Requirements

- Python **3.12+**
- [Spotify Developer](https://developer.spotify.com/dashboard) app (Client ID and Client Secret)
- Spotify account with an active session while using the app

### Platform notes

| OS | Extra packages / tools |
|----|-------------------------|
| **Windows** | None (uses `ctypes`) |
| **macOS** | `pip install -e ".[macos]"` for `appscript`; optional PyObjC (`pyobjc-framework-Cocoa`) for all-screen AppKit control |
| **Linux GNOME / Unity / Budgie / Cinnamon** | `gsettings`, D-Bus session (usually already installed) |
| **Linux KDE** | `plasma-apply-wallpaperimage` or `qdbus6` / `qdbus` |
| **Other Linux WMs** | One of `feh`, `swaybg`, or `nitrogen`; `xrandr` or `wlr-randr` for screen size |

## Setup

```bash
git clone https://github.com/hippi345/nowPlayingDesktops.git
cd nowPlayingDesktops
python3.12 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

On macOS:

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

```bash
now-playing run YOUR_SPOTIFY_USERNAME
```

Legacy entry points `now-playing-macos` and `now-playing-windows` still work.

- **`now-playing run USER [--once]`** — poll Spotify and update the wallpaper.
- **`now-playing restore`** — restore the wallpaper saved at session start (uses path or platform snapshot).
- **`now-playing autostart enable|disable|status`** — register login autostart (replace `YOUR_SPOTIFY_USERNAME` in the macOS LaunchAgent manually after enabling, if needed).

On first run, Spotipy opens a browser flow for `user-read-currently-playing`. Stop with `Ctrl+C`; the original wallpaper is restored automatically.

## Restore and crash recovery

Session state lives in the app cache (see `state_file_path()` in `config.py`). On startup, if a previous run exited without restoring (`session_active`), the runner restores immediately. Linux GNOME restores `picture-uri` / `picture-uri-dark`; KDE and WM fallbacks restore via their saved snapshots.

## Troubleshooting

| Issue | What to try |
|-------|-------------|
| Linux “unsupported platform” | Install `feh`, `swaybg`, or `nitrogen`, or run under GNOME/KDE with `gsettings` / Plasma tools available |
| Wallpaper does not update on GNOME | Ensure a D-Bus session (`echo $DBUS_SESSION_BUS_ADDRESS`) |
| KDE script errors | Install `plasma-apply-wallpaperimage` or `qdbus6` |
| macOS only primary screen changes | Install PyObjC Cocoa bindings or rely on `osascript` (default fallback) |
| Windows wrong resolution | DPI awareness is enabled automatically; wallpaper is composed at the largest monitor size when per-monitor COM is unavailable |

## Development

```bash
pip install -e ".[dev]"
ruff check src tests
ruff format src tests
pytest -q
python -m build
```

Integration tests (`pytest -m integration`) exercise GNOME `gsettings` under `dbus-run-session` and `feh` under `xvfb-run` when those tools are installed (CI installs them on Ubuntu).

## Project structure

```
.github/workflows/ci.yml
src/now_playing_desktops/
  platforms/          # Windows, macOS, Linux backends + autostart
  composer.py         # Wallpaper image composition
  runner.py           # Spotify loop + restore
tests/
```

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 Joel Shearon.
