"""Command-line entry points."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from now_playing_desktops.auth import create_spotify_client
from now_playing_desktops.config import (
    DEFAULT_POLL_INTERVAL_SECONDS,
    default_cache_dir,
    state_file_path,
)
from now_playing_desktops.platforms import UnsupportedPlatformError, get_platform
from now_playing_desktops.runner import NowPlayingRunner, RunnerDeps


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _shared_verbose_parser() -> argparse.ArgumentParser:
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    return shared


def build_parser() -> argparse.ArgumentParser:
    shared = _shared_verbose_parser()
    parser = argparse.ArgumentParser(
        prog="now-playing-desktops",
        description="Set your desktop wallpaper to the currently playing Spotify track.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        "run",
        help="Poll Spotify and update the wallpaper.",
        parents=[shared],
    )
    run_parser.add_argument("username", help="Spotify username for OAuth")
    run_parser.add_argument(
        "--poll-interval",
        type=float,
        default=DEFAULT_POLL_INTERVAL_SECONDS,
        help=f"Seconds between polls (default {DEFAULT_POLL_INTERVAL_SECONDS}).",
    )
    run_parser.add_argument(
        "--once",
        action="store_true",
        help="Perform a single poll/apply cycle and exit.",
    )
    run_parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="Override the composed-art cache directory.",
    )

    restore_parser = subparsers.add_parser(
        "restore",
        help="Restore the wallpaper saved at startup.",
        parents=[shared],
    )
    restore_parser.add_argument(
        "--state-file",
        type=Path,
        default=None,
        help="Override the session state file path.",
    )

    autostart_parser = subparsers.add_parser(
        "autostart",
        help="Enable or disable login autostart for the wallpaper runner.",
        parents=[shared],
    )
    autostart_parser.add_argument(
        "action",
        choices=("enable", "disable", "status"),
        help="Register, remove, or query autostart.",
    )
    return parser


def _run(args: argparse.Namespace) -> int:
    try:
        platform = get_platform()
    except UnsupportedPlatformError as exc:
        print(exc, file=sys.stderr)
        return 1

    client_bundle = create_spotify_client(args.username)
    if client_bundle is None:
        print("Can't get token for", args.username, file=sys.stderr)
        return 1
    sp, _manager, refresh = client_bundle

    cache_dir = args.cache_dir or default_cache_dir()
    runner = NowPlayingRunner(
        RunnerDeps(
            platform=platform,
            sp=sp,
            cache_dir=cache_dir,
            state_path=state_file_path(),
            poll_interval_seconds=args.poll_interval,
            on_token_refresh=refresh,
        )
    )

    try:
        if args.once:
            runner.startup()
            runner.apply_playback_once()
            return 0
        runner.run_forever()
    except KeyboardInterrupt:
        runner.restore_original_wallpaper()
        return 0
    return 0


def _autostart(args: argparse.Namespace) -> int:
    from now_playing_desktops.platforms.autostart import (
        autostart_enabled,
        disable_autostart,
        enable_autostart,
    )

    if args.action == "status":
        print("enabled" if autostart_enabled() else "disabled")
        return 0
    if args.action == "enable":
        enable_autostart()
        print("Autostart enabled")
        return 0
    disable_autostart()
    print("Autostart disabled")
    return 0


def _restore(args: argparse.Namespace) -> int:
    try:
        platform = get_platform()
    except UnsupportedPlatformError as exc:
        print(exc, file=sys.stderr)
        return 1

    runner = NowPlayingRunner(
        RunnerDeps(
            platform=platform,
            sp=object(),
            cache_dir=default_cache_dir(),
            state_path=args.state_file or state_file_path(),
            poll_interval_seconds=DEFAULT_POLL_INTERVAL_SECONDS,
        )
    )
    if runner.restore_original_wallpaper():
        return 0
    print("nothing to restore")
    return 0


def _argv_requests_verbose(argv: list[str]) -> bool:
    return any(token in {"-v", "--verbose"} for token in argv)


def main(argv: list[str] | None = None) -> int:
    argv = list(argv) if argv is not None else sys.argv[1:]
    parser = build_parser()
    args = parser.parse_args(argv)
    verbose = bool(getattr(args, "verbose", False)) or _argv_requests_verbose(argv)
    _configure_logging(verbose)
    if args.command == "run":
        return _run(args)
    if args.command == "restore":
        return _restore(args)
    if args.command == "autostart":
        return _autostart(args)
    parser.error(f"Unknown command {args.command!r}")
    return 2


def _legacy_argv() -> list[str]:
    argv = sys.argv[1:]
    if argv and argv[0] not in {"run", "restore", "autostart"}:
        return ["run", *argv]
    return argv


def main_macos() -> None:
    """Legacy console script entry point."""
    raise SystemExit(main(_legacy_argv()))


def main_windows() -> None:
    """Legacy console script entry point."""
    raise SystemExit(main(_legacy_argv()))


if __name__ == "__main__":
    raise SystemExit(main())
