"""Application logging: console plus rotating file log with uncaught exception hooks."""

from __future__ import annotations

import logging
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

from now_playing_desktops.config import user_config_dir

LOG_FILENAME = "now-playing.log"
_MAX_BYTES = 2 * 1024 * 1024
_BACKUP_COUNT = 5

_configured = False
_file_handler: RotatingFileHandler | None = None


def log_file_path() -> Path:
    return user_config_dir() / "logs" / LOG_FILENAME


def install_exception_logging() -> None:
    """Route uncaught main-thread and worker-thread exceptions to the app log."""

    def _log_exception(exc_type, exc, tb) -> None:
        if exc_type is KeyboardInterrupt:
            sys.__excepthook__(exc_type, exc, tb)
            return
        logging.getLogger("now_playing_desktops").critical(
            "Uncaught exception",
            exc_info=(exc_type, exc, tb),
        )

    sys.excepthook = _log_exception

    if hasattr(threading, "excepthook"):
        previous = threading.excepthook

        def _thread_hook(args: threading.ExceptHookArgs) -> None:
            logging.getLogger("now_playing_desktops").critical(
                "Uncaught thread exception in %s",
                args.thread.name if args.thread else "unknown",
                exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
            )
            if previous is not None:
                previous(args)

        threading.excepthook = _thread_hook


def configure_application_logging(
    *,
    verbose: bool = False,
    enable_file_log: bool = False,
) -> Path | None:
    """
    Configure root logging once per process.

    ``enable_file_log`` is on for long-running/background ``run`` sessions so
    pythonw/autostart errors are not lost.
    """
    global _configured, _file_handler
    level = logging.DEBUG if verbose else logging.INFO
    root = logging.getLogger()
    root.setLevel(level)

    if not _configured:
        console = logging.StreamHandler()
        console.setLevel(level)
        console.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"),
        )
        root.addHandler(console)
        install_exception_logging()
        _configured = True
    else:
        for handler in root.handlers:
            handler.setLevel(level)

    file_path: Path | None = None
    if enable_file_log:
        file_path = log_file_path()
        file_path.parent.mkdir(parents=True, exist_ok=True)
        if _file_handler is None:
            _file_handler = RotatingFileHandler(
                file_path,
                maxBytes=_MAX_BYTES,
                backupCount=_BACKUP_COUNT,
                encoding="utf-8",
            )
            _file_handler.setLevel(logging.DEBUG)
            _file_handler.setFormatter(
                logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"),
            )
            root.addHandler(_file_handler)
        logging.getLogger(__name__).info("File logging enabled: %s", file_path)

    return file_path
