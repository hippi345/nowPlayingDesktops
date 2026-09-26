# Security Policy

## Supported versions

Security fixes are applied on the latest release on the default branch.

## Reporting a vulnerability

Please open a [GitHub Security Advisory](https://github.com/hippi345/nowPlayingDesktops/security/advisories/new) or contact the repository owner privately. Do not open public issues for undisclosed vulnerabilities.

## Secrets and credentials

- Never commit Spotify `client_id`, `client_secret`, or OAuth tokens.
- Configure credentials via environment variables (`SPOTIPY_CLIENT_ID`, `SPOTIPY_CLIENT_SECRET`, `SPOTIPY_REDIRECT_URI`).
- If credentials were ever committed to git history, rotate them in the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) immediately.
