"""Allow ``python -m now_playing_desktops``."""

import sys

if sys.platform == "win32":
    from now_playing_desktops.platforms.windows_dpi import set_process_dpi_aware

    set_process_dpi_aware()

from now_playing_desktops.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
