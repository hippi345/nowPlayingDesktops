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
- [Spotify Developer](https://developer.spotify.com/dashboard) app (Client ID; Client Secret optional — see Setup)
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

Copy the example environment file and add your Spotify app **Client ID**:

```bash
cp .env.example .env
# Edit .env — never commit real secrets
export $(grep -v '^#' .env | xargs)   # optional in an interactive shell
```

**PKCE (recommended):** leave `SPOTIPY_CLIENT_SECRET` unset, add the loopback redirect URI in the Spotify dashboard (below), then run `now-playing login YOUR_SPOTIFY_USERNAME` once. Background `run` and login autostart reuse the cached token and refresh it silently.

**Legacy client-secret flow:** set `SPOTIPY_CLIENT_SECRET` in `.env` as well; the app keeps the previous Spotipy behavior (browser sign-in on first `run` if needed).

Apps in [Development mode](https://developer.spotify.com/documentation/web-api/concepts/quota-modes) only work for users on the app's allowlist (Dashboard → your app → Settings → **Users Management**). Spotify currently allows up to **five** authorized users per Development mode app (plus the owner). Extended quota mode is required for wider distribution.

For **login autostart**, the app does not inherit your shell environment. Put a copy of `.env` in the per-user config directory (loaded automatically at startup):

| OS | Autostart `.env` path |
|----|------------------------|
| **Windows** | `%APPDATA%\now-playing-desktops\.env` |
| **macOS** | `~/Library/Application Support/now-playing-desktops/.env` |
| **Linux** | `$XDG_CONFIG_HOME/now-playing-desktops/.env` (default `~/.config/now-playing-desktops/.env`) |

You can also pass `--env-file PATH` on `run` and `autostart enable`, or set `NOW_PLAYING_ENV_FILE` to a file path.

| Variable | Required | Description |
|----------|----------|-------------|
| `SPOTIPY_CLIENT_ID` | Yes | Spotify app Client ID |
| `SPOTIPY_CLIENT_SECRET` | No | Client Secret (legacy flow only; omit for PKCE) |
| `SPOTIPY_REDIRECT_URI` | No | OAuth redirect (default `http://127.0.0.1:8897/callback`) |
| `SPOTIPY_CLIENT_USERNAME` | No | Spotify username (token cache key; recommended for autostart) |

In the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard), open your app → **Settings** → **Redirect URIs** and add this exact URI (unless you override `SPOTIPY_REDIRECT_URI`):

`http://127.0.0.1:8897/callback`

If another program is already listening on that port, set `SPOTIPY_REDIRECT_URI` to a free loopback port (for example `http://127.0.0.1:8898/callback`) and add the same URI in the Spotify dashboard.

## Usage

```bash
now-playing login YOUR_SPOTIFY_USERNAME   # once, PKCE or legacy
now-playing run YOUR_SPOTIFY_USERNAME
```

Legacy entry points `now-playing-macos` and `now-playing-windows` still work.

- **`now-playing login [USER] [--env-file PATH]`** — interactive Spotify sign-in; stores a per-user token cache under your app config directory.
- **`now-playing run [USER] [--once] [--env-file PATH]`** — poll Spotify and update the wallpaper. `USER` is optional when `SPOTIPY_CLIENT_USERNAME` is set (recommended in your autostart `.env`). PKCE runs expect a prior `login`; legacy client-secret runs may still open a browser on first start.
- **`now-playing restore`** — restore the wallpaper saved at session start (uses path or platform snapshot).
- **`now-playing diag`** — (Windows) print Spotify auth mode and token-cache status, plus monitor sizes, DPI, compose canvas, wallpaper style, and registry state (no secrets printed).
- **`now-playing autostart enable [USER] [--env-file PATH]|disable|status`** — register login autostart. `enable` writes an absolute `--env-file` path and your Spotify username into the Windows Run entry, XDG autostart `.desktop`, or macOS LaunchAgent (see autostart `.env` paths above).

Stop with `Ctrl+C`; the original wallpaper is restored automatically.

## Restore and crash recovery

Session state lives in the app cache (see `state_file_path()` in `config.py`). On startup, if a previous run exited without restoring (`session_active`), the runner restores immediately. Linux GNOME restores `picture-uri` / `picture-uri-dark`; KDE and WM fallbacks restore via their saved snapshots.

## Troubleshooting

| Issue | What to try |
|-------|-------------|
| Linux “unsupported platform” | Install `feh`, `swaybg`, or `nitrogen`, or run under GNOME/KDE with `gsettings` / Plasma tools available |
| Wallpaper does not update on GNOME | Ensure a D-Bus session (`echo $DBUS_SESSION_BUS_ADDRESS`) |
| KDE script errors | Install `plasma-apply-wallpaperimage` or `qdbus6` |
| macOS only primary screen changes | Install PyObjC Cocoa bindings or rely on `osascript` (default fallback) |
| Windows wrong resolution | Run `now-playing diag` and check `dmPels` vs compose canvas; delete stale `%APPDATA%\\now-playing-desktops\\cache\\composed\\*.png` after upgrades |
| Autostart errors with no console | See `%APPDATA%\\now-playing-desktops\\logs\\now-playing.log` (rotating file log; same path under the platform config dir on Linux/macOS) |
| OAuth “port in use” / WinError 10013 | Set `SPOTIPY_REDIRECT_URI` to another `127.0.0.1` port and register it in the Spotify dashboard |
| PKCE `run` says to run `login` | Run `now-playing login` with the same `--env-file` and username once |

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
