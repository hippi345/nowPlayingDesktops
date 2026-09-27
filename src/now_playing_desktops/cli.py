"""Command-line entry points."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

if sys.platform == "win32":
    from now_playing_desktops.platforms.windows_dpi import (
        set_process_dpi_aware as _win32_dpi_bootstrap,
    )

    _win32_dpi_bootstrap()

from now_playing_desktops.auth import (
    create_spotify_client,
    interactive_sign_in,
    spotify_auth_diag_lines,
)
from now_playing_desktops.config import (
    DEFAULT_POLL_INTERVAL_SECONDS,
    default_cache_dir,
    state_file_path,
    user_config_dir,
)
from now_playing_desktops.env_loader import load_environment, resolve_spotify_username
from now_playing_desktops.logging_setup import configure_application_logging
from now_playing_desktops.platforms import UnsupportedPlatformError, get_platform
from now_playing_desktops.runner import NowPlayingRunner, RunnerDeps


def _configure_logging(verbose: bool, *, command: str) -> None:
    configure_application_logging(
        verbose=verbose,
        enable_file_log=command == "run",
    )


def _peek_command_and_verbose(argv: list[str]) -> tuple[str, bool]:
    verbose = _argv_requests_verbose(argv)
    command = "run"
    for token in argv:
        if token in {"run", "restore", "autostart", "diag", "login"}:
            command = token
            break
    return command, verbose


def _shared_verbose_parser() -> argparse.ArgumentParser:
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    shared.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="Load Spotify OAuth settings from this .env file (see README).",
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
    run_parser.add_argument(
        "username",
        nargs="?",
        default=None,
        help="Spotify username for OAuth (optional if SPOTIPY_CLIENT_USERNAME is set).",
    )
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
    autostart_parser.add_argument(
        "username",
        nargs="?",
        default=None,
        help="Spotify username to embed in autostart (optional if SPOTIPY_CLIENT_USERNAME is set).",
    )

    login_parser = subparsers.add_parser(
        "login",
        help="Interactive Spotify sign-in (stores a token cache for background runs).",
        parents=[shared],
    )
    login_parser.add_argument(
        "username",
        nargs="?",
        default=None,
        help="Spotify username for OAuth (optional if SPOTIPY_CLIENT_USERNAME is set).",
    )

    subparsers.add_parser(
        "diag",
        help="Print Windows display/wallpaper diagnostics (no Spotify credentials).",
        parents=[shared],
    )
    return parser


def _run(args: argparse.Namespace) -> int:
    from now_playing_desktops.single_instance import ensure_single_run_instance

    run_lock = ensure_single_run_instance()
    if run_lock is None:
        return 0
    try:
        return _run_with_lock(args)
    finally:
        run_lock.release()


def _run_with_lock(args: argparse.Namespace) -> int:
    try:
        platform = get_platform()
    except UnsupportedPlatformError as exc:
        print(exc, file=sys.stderr)
        return 1

    username = resolve_spotify_username(args.username)
    if username is None:
        print(
            "Spotify username required: pass it on the command line or set "
            "SPOTIPY_CLIENT_USERNAME.",
            file=sys.stderr,
        )
        return 1
    client_bundle = create_spotify_client(username)
    if client_bundle is None:
        print("Can't get token for", username, file=sys.stderr)
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
        AutostartSetupError,
        autostart_enabled,
        disable_autostart,
        enable_autostart,
    )

    if args.action == "status":
        print("enabled" if autostart_enabled() else "disabled")
        return 0
    if args.action == "enable":
        try:
            enable_autostart(env_file=args.env_file, username=args.username)
        except AutostartSetupError as exc:
            print(exc, file=sys.stderr)
            return 1
        print("Autostart enabled")
        return 0
    disable_autostart()
    print("Autostart disabled")
    return 0


def _login(args: argparse.Namespace) -> int:
    username = resolve_spotify_username(args.username)
    if username is None:
        print(
            "Spotify username required: pass it on the command line or set "
            "SPOTIPY_CLIENT_USERNAME.",
            file=sys.stderr,
        )
        return 1
    token = interactive_sign_in(username)
    if token is None:
        print("Spotify sign-in failed for", username, file=sys.stderr)
        return 1
    print("Spotify sign-in succeeded.")
    return 0


def _diag(args: argparse.Namespace) -> int:
    if sys.platform != "win32":
        print("diag is only available on Windows", file=sys.stderr)
        return 1
    from now_playing_desktops.platforms.windows_diag import (
        collect_windows_diag_report,
        format_windows_diag_report,
    )
    from now_playing_desktops.platforms.windows_dpi import bootstrap_process_dpi_awareness

    bootstrap_process_dpi_awareness()
    username = resolve_spotify_username(getattr(args, "username", None))
    auth_lines = spotify_auth_diag_lines(username)
    report = collect_windows_diag_report()
    print("\n".join([*auth_lines, "", format_windows_diag_report(report)]))
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


def _resolve_env_file_path(explicit: Path | None) -> Path | None:
    if explicit is None:
        return None
    return explicit.expanduser().resolve()


def _ensure_runtime_working_directory() -> None:
    """Match autostart/login sessions: run with the app config dir as cwd."""
    target = user_config_dir()
    target.mkdir(parents=True, exist_ok=True)
    try:
        import os

        os.chdir(target)
    except OSError:
        logging.getLogger(__name__).warning(
            "Could not chdir to %s; relative asset paths may fail",
            target,
        )


def main(argv: list[str] | None = None) -> int:
    if sys.platform == "win32":
        from now_playing_desktops.platforms.windows_dpi import set_process_dpi_aware

        set_process_dpi_aware()
    argv = list(argv) if argv is not None else sys.argv[1:]
    command, verbose_from_argv = _peek_command_and_verbose(argv)
    parser = build_parser()
    args = parser.parse_args(argv)
    verbose = bool(getattr(args, "verbose", False)) or verbose_from_argv
    _configure_logging(verbose, command=command)
    env_file = _resolve_env_file_path(getattr(args, "env_file", None))
    load_environment(explicit=env_file, verbose=verbose)
    if args.command in {"run", "restore"}:
        _ensure_runtime_working_directory()
    if args.command == "run":
        return _run(args)
    if args.command == "restore":
        return _restore(args)
    if args.command == "autostart":
        return _autostart(args)
    if args.command == "login":
        return _login(args)
    if args.command == "diag":
        return _diag(args)
    parser.error(f"Unknown command {args.command!r}")
    return 2


def _legacy_argv() -> list[str]:
    argv = sys.argv[1:]
    if argv and argv[0] not in {"run", "restore", "autostart", "diag", "login"}:
        return ["run", *argv]
    return argv


def main_macos() -> None:
    """Legacy console script entry point."""
    raise SystemExit(main(_legacy_argv()))


def main_windows() -> None:
    """Legacy console script entry point."""
    if sys.platform == "win32":
        from now_playing_desktops.platforms.windows_dpi import set_process_dpi_aware

        set_process_dpi_aware()
    raise SystemExit(main(_legacy_argv()))


if __name__ == "__main__":
    raise SystemExit(main())
