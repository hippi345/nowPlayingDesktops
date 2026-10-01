"""PyInstaller entry point for the Linux console build."""

from now_playing_desktops.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
