# nowPlayingDesktops

[![CI](https://github.com/hippi345/nowPlayingDesktops/actions/workflows/ci.yml/badge.svg)](https://github.com/hippi345/nowPlayingDesktops/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Set your desktop wallpaper to the album art of whatever you are playing on Spotify (or another supported desktop player in **local** mode).

## Which mode should I pick?

| Mode | Command | What it needs | Players / devices | Account / app setup | Pros | Cons |
|------|---------|---------------|-------------------|----------------------|------|------|
| **Local** | `--source local` | Python 3.12+, platform extras (see below), media app **playing on this computer** | Spotify desktop (Windows SMTC, Linux MPRIS, macOS AppleScript); other MPRIS players on Linux may work if they expose metadata | None | No Spotify Developer app; no OAuth; works offline for playback detection | Art is often a small system thumbnail unless online art is enabled; desktop app must be on this machine |
| **Spotify** | `--source spotify` | Same Python install + `SPOTIPY_CLIENT_ID` in `.env` | Any device where **your** Spotify account is playing (phone, web, desktop, etc.) | [Spotify Developer](https://developer.spotify.com/dashboard) app; PKCE `login` once; Development mode **user allowlist** (up to 5 users) | High-resolution album art from the Web API | Requires Spotify credentials and allowlisted users in dev mode |
| **Auto** | `--source auto` (default) | If `SPOTIPY_CLIENT_ID` is set → Spotify mode; otherwise → local | Same as the effective mode | Same as the effective mode | Convenient default when you already have a `.env` | Surprising if you expected local but have a Client ID configured |

Legacy console scripts `now-playing-macos` and `now-playing-windows` behave like `now-playing run …` when you omit the `run` subcommand.

---

## Quick Start: Local mode

### Requirements

- **Python 3.12+** (`requires-python` in `pyproject.toml`; CI tests 3.12 and 3.13).
- A **desktop media player** playing on the same machine (Spotify desktop is the primary target).

### Install

```bash
git clone https://github.com/hippi345/nowPlayingDesktops.git
cd nowPlayingDesktops
python3.12 -m venv .venv
```

Activate the venv:

- **Linux / macOS:** `source .venv/bin/activate`
- **Windows (PowerShell):** `.\.venv\Scripts\Activate.ps1`

Install with the extras for your OS (add `dev` if you are developing):

| OS | Install command |
|----|-----------------|
| **Windows** | `pip install -e ".[windows]"` |
| **macOS** | `pip install -e ".[macos]"` |
| **Linux** | `pip install -e ".[linux]"` |

### Platform notes for local playback

| OS | How local mode reads playback | Notes |
|----|----------------------------------|-------|
| **Windows** | System Media Transport Controls (SMTC) for Spotify | Requires the `[windows]` WinRT optional dependencies |
| **Linux** | MPRIS over D-Bus (`org.mpris.MediaPlayer2.spotify`) | Requires `[linux]` (`dbus-next`). You need a **D-Bus session** (`echo $DBUS_SESSION_BUS_ADDRESS`). Tools such as `playerctl` are not required by this app, but your player must expose MPRIS. |
| **macOS** | AppleScript to **Spotify.app** | Requires `[macos]` (`appscript`). macOS may prompt for **Automation** permission for your terminal/Python to control Spotify (System Settings → Privacy & Security → Automation). |

### Run

Start Spotify (or another supported player) and begin playback, then:

```bash
now-playing run YOUR_SPOTIFY_USERNAME --source local
```

`YOUR_SPOTIFY_USERNAME` is optional in local mode (it is only required for `--source spotify`). A typical local-only invocation:

```bash
now-playing run --source local
```

Optional flags you may use with `run`:

- `-v` / `--verbose` — debug logging
- `--once` — single poll/apply cycle
- `--env-file PATH` — load settings from a `.env` file
- `--no-online-art` — do not fetch album art over the internet (see [Album art](#album-art-in-local-mode))
- `--poll-interval SECONDS` — default `2.5`

### Login autostart (local)

```bash
now-playing autostart enable YOUR_SPOTIFY_USERNAME --source local
```

`enable` forwards `--source`, `--env-file`, `--no-online-art`, and the username into the registered autostart command (Windows Run key, XDG autostart `.desktop`, or macOS LaunchAgent). Check status with `now-playing autostart status`; remove with `now-playing autostart disable`.

---

## Album art in local mode

When **online art is enabled** (default), cover resolution is:

1. **System media thumbnail** when available (SMTC on Windows, MPRIS art on Linux, AppleScript artwork URL on macOS — URL download only if online art is enabled).
2. **[Apple iTunes Search API](https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/)** (public HTTPS; no iTunes app or Apple account required) to find higher-resolution artwork when the thumbnail is small.
3. **Generated placeholder** (gradient + track title/artist) if nothing else is available.

A background thread may **upgrade** wallpaper art after the first apply when iTunes returns a larger image for the same playing track (see logs: `Upgraded art Apply took …`).

### Disable online art (offline / privacy)

Set in your environment or `.env` file:

```bash
NOW_PLAYING_ONLINE_ART=0
```

Or pass on the CLI:

```bash
now-playing run --source local --no-online-art
```

When disabled: use local thumbnails only, then placeholder; **no** iTunes requests, **no** Spotify art URL downloads, **no** background iTunes upgrader. (Spotify **Web API** mode still uses the network for playback and API album art unless you also use `--no-online-art`, which skips art URL downloads and uses placeholders.)

The app loads `.env` from (first match wins, without overriding variables already set in the shell):

1. `--env-file` / `NOW_PLAYING_ENV_FILE`
2. Per-user config: `%APPDATA%\now-playing-desktops\.env` (Windows), `~/Library/Application Support/now-playing-desktops/.env` (macOS), `$XDG_CONFIG_HOME/now-playing-desktops/.env` (Linux, default `~/.config/now-playing-desktops/.env`)
3. Current working directory `.env`

---

## Quick Start: Spotify mode

### 1. Create a Spotify app

1. Open the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) and create an app.
2. Copy the **Client ID** (PKCE does **not** need a Client Secret).
3. Under **Settings** → **Redirect URIs**, add this exact URI (unless you override it):

   `http://127.0.0.1:8897/callback`

   This is the default from `SPOTIPY_REDIRECT_URI` / `DEFAULT_REDIRECT_URI` in `auth.py`. If port `8897` is in use, pick another loopback URL (for example `http://127.0.0.1:8898/callback`), set `SPOTIPY_REDIRECT_URI` to match, and register the same URI in the dashboard.

### 2. Configure credentials

Copy `.env.example` to `.env` or to the per-user config path (recommended for autostart):

| OS | Config directory |
|----|------------------|
| **Windows** | `%APPDATA%\now-playing-desktops\.env` |
| **macOS** | `~/Library/Application Support/now-playing-desktops/.env` |
| **Linux** | `~/.config/now-playing-desktops/.env` |

Minimum for PKCE:

```env
SPOTIPY_CLIENT_ID=your_client_id_here
SPOTIPY_CLIENT_USERNAME=your_spotify_username
```

### 3. Allowlist users (Development mode)

Apps in [Development mode](https://developer.spotify.com/documentation/web-api/concepts/quota-modes) only work for users listed under the app’s **Users Management** (currently up to **five** users plus the owner). Add every Spotify account that will use the app.

### 4. Sign in once

```bash
now-playing login YOUR_SPOTIFY_USERNAME
```

Optional: `--env-file PATH` if your `.env` is not in the default config directory.

Token cache file: `spotify-token-<username>.cache` under the same config directory (`config.spotify_token_cache_path`).

### 5. Run

```bash
now-playing run YOUR_SPOTIFY_USERNAME --source spotify
```

Autostart:

```bash
now-playing autostart enable YOUR_SPOTIFY_USERNAME --source spotify
```

(`enable` requires Spotify credentials in the resolved `.env` when source is `spotify` or `auto` with Client ID present.)

---

## Command reference

| Command | Purpose |
|---------|---------|
| `now-playing run [USER] [--source spotify\|local\|auto] [--once] [--env-file PATH] [--no-online-art] [-v]` | Poll playback and update wallpaper |
| `now-playing login [USER] [--env-file PATH] [-v]` | Interactive Spotify OAuth (PKCE or legacy secret flow) |
| `now-playing restore [--state-file PATH] [-v]` | Restore wallpaper saved at session start |
| `now-playing diag [-v]` | **Windows only:** playback source diagnostics, Spotify auth summary, monitor/DPI/wallpaper report |
| `now-playing autostart enable [USER] [--source …] [--env-file PATH] [--no-online-art] [-v]` | Register login autostart |
| `now-playing autostart disable` | Remove autostart |
| `now-playing autostart status` | Print `enabled` or `disabled` |

Stop a foreground `run` with `Ctrl+C`; the original wallpaper is restored automatically.

---

## Wallpaper behavior

- Composes a blurred backdrop, glass panel, cover art, and track labels; restores your original wallpaper on pause or exit.
- **Windows** — multi-monitor aware; optional per-monitor wallpaper when `IDesktopWallpaper` is available.
- **macOS** — sets wallpaper on every display (AppKit / `osascript`).
- **Linux** — GNOME (`gsettings`), KDE (`plasma-apply-wallpaperimage` / `qdbus`), or fallbacks (`feh`, `swaybg`, `nitrogen`).

Session state: `wallpaper-state.json` in the config directory. If a previous run exited without restoring (`session_active`), the next startup restores immediately.

---

## Troubleshooting

| Topic | What to do |
|-------|------------|
| **`now-playing diag`** | Windows only. Shows effective playback source, what local/Spotify sources see, auth mode, and display/wallpaper geometry. |
| **Log file** | During `run`, logging goes to a rotating file: `%APPDATA%\now-playing-desktops\logs\now-playing.log` on Windows; the same relative path under the platform config dir on macOS/Linux (`user_config_dir() / "logs" / "now-playing.log"`). |
| **Single instance** | Only one `now-playing run` at a time. A second instance logs: `Another now-playing run instance is already active (...); exiting` and exits 0. Stop the existing run (Ctrl+C in its terminal) or end that process; on Windows you can find it with `Get-CimInstance Win32_Process` and filter `CommandLine` for `now_playing`. |
| **Verbose** | `-v` / `--verbose` on any subcommand that accepts shared flags. |
| **Compose quality checks** | Set `NOW_PLAYING_COMPOSE_VERIFY=1` to run optional post-apply checks in a background thread (never blocks wallpaper set). |
| **Apply timing** | Look for `Apply took X.XXs (fetch=…, compose=…, save=…, set=…, cache=hit\|miss)` in logs; background upgrades log `Upgraded art Apply took …`. |
| **Linux unsupported platform** | Install `feh`, `swaybg`, or `nitrogen`, or use GNOME/KDE with their wallpaper tools. |
| **Local mode: no track** | Start the desktop player and press play; on Windows install `pip install -e ".[windows]"`. |
| **OAuth port in use** | Change `SPOTIPY_REDIRECT_URI` and register the new URI in the Spotify dashboard. |

---

## Development

```bash
pip install -e ".[dev]"
ruff check src tests
ruff format src tests
pytest -q
```

Profile compose at laptop resolution: `python scripts/profile_compose.py`.

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 Joel Shearon.
