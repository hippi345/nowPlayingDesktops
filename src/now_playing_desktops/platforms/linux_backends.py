"""Linux wallpaper backends (GNOME, KDE, feh, swaybg, nitrogen)."""

from __future__ import annotations

import configparser
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import quote

from now_playing_desktops.platforms.linux_screen import path_from_file_uri

_GNOME_BG_SCHEMA = "org.gnome.desktop.background"
_GNOME_KEYS = ("picture-uri", "picture-uri-dark", "picture-options")


def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=check,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _which(name: str) -> str | None:
    return shutil.which(name)


def path_to_file_uri(path: Path) -> str:
    resolved = path.resolve()
    return "file://" + quote(resolved.as_posix(), safe="/:")


class GnomeWallpaperBackend:
    """GNOME / Mutter family via gsettings."""

    def capture_snapshot(self) -> dict[str, Any]:
        values: dict[str, str] = {}
        for key in _GNOME_KEYS:
            proc = _run(["gsettings", "get", _GNOME_BG_SCHEMA, key], check=False)
            if proc.returncode == 0:
                values[key] = proc.stdout.strip()
        path = None
        if "picture-uri" in values:
            path = path_from_file_uri(values["picture-uri"].strip("'\""))
        return {
            "backend": "gnome",
            "gsettings": values,
            "path": str(path) if path else None,
        }

    def apply_snapshot(self, snapshot: dict[str, Any]) -> None:
        gsettings = snapshot.get("gsettings") or {}
        for key in _GNOME_KEYS:
            if key in gsettings:
                _run(["gsettings", "set", _GNOME_BG_SCHEMA, key, gsettings[key]])

    def set_wallpaper(self, path: Path) -> None:
        uri = path_to_file_uri(path)
        quoted = f"'{uri}'"
        _run(["gsettings", "set", _GNOME_BG_SCHEMA, "picture-uri", quoted])
        _run(["gsettings", "set", _GNOME_BG_SCHEMA, "picture-uri-dark", quoted])
        options = "zoom"
        try:
            proc = _run(
                ["gsettings", "get", _GNOME_BG_SCHEMA, "picture-options"],
                check=False,
            )
            if proc.returncode == 0 and proc.stdout.strip() in {"'scaled'", "'stretched'"}:
                options = "scaled"
        except OSError:
            pass
        _run(["gsettings", "set", _GNOME_BG_SCHEMA, "picture-options", f"'{options}'"])

    def get_current_wallpaper(self) -> Path | None:
        proc = _run(["gsettings", "get", _GNOME_BG_SCHEMA, "picture-uri"], check=False)
        if proc.returncode != 0:
            return None
        return path_from_file_uri(proc.stdout.strip().strip("'\""))


class KdeWallpaperBackend:
    """KDE Plasma via plasma-apply-wallpaperimage or qdbus script."""

    def _plasma_config_path(self) -> Path:
        return Path.home() / ".config" / "plasma-org.kde.plasma.desktop-appletsrc"

    def _read_image_from_config(self) -> Path | None:
        cfg_path = self._plasma_config_path()
        if not cfg_path.is_file():
            return None
        parser = configparser.ConfigParser(interpolation=None)
        parser.optionxform = str  # type: ignore[method-assign]
        try:
            parser.read(cfg_path, encoding="utf-8")
        except (OSError, configparser.Error):
            return None
        for section in parser.sections():
            if parser.has_option(section, "Image"):
                raw = parser.get(section, "Image")
                if raw:
                    candidate = Path(raw).expanduser()
                    if candidate.is_file():
                        return candidate
        return None

    def capture_snapshot(self) -> dict[str, Any]:
        path = self._read_image_from_config() or self.get_current_wallpaper()
        return {
            "backend": "kde",
            "path": str(path) if path else None,
        }

    def apply_snapshot(self, snapshot: dict[str, Any]) -> None:
        raw = snapshot.get("path")
        if raw:
            self.set_wallpaper(Path(raw))

    def set_wallpaper(self, path: Path) -> None:
        resolved = str(path.resolve())
        if _which("plasma-apply-wallpaperimage"):
            _run(["plasma-apply-wallpaperimage", resolved])
            return
        script = (
            "var allDesktops = desktops();"
            f"for (var i = 0; i < allDesktops.length; i++) {{"
            f"  allDesktops[i].wallpaperPlugin = 'org.kde.image';"
            f"  allDesktops[i].currentConfigGroup = ['Wallpaper',"
            f" 'org.kde.image', 'General'];"
            f"  allDesktops[i].writeConfig('Image', 'file://{resolved}');"
            "}"
        )
        for qdbus in ("qdbus6", "qdbus"):
            if _which(qdbus):
                _run(
                    [
                        qdbus,
                        "org.kde.plasmashell",
                        "/PlasmaShell",
                        "org.kde.PlasmaShell.evaluateScript",
                        script,
                    ]
                )
                return
        raise OSError("No plasma-apply-wallpaperimage or qdbus available for KDE")

    def get_current_wallpaper(self) -> Path | None:
        return self._read_image_from_config()


class FehWallpaperBackend:
    """feh --bg-fill with restore via ~/.fehbg."""

    def capture_snapshot(self) -> dict[str, Any]:
        fehbg = Path.home() / ".fehbg"
        content = fehbg.read_text(encoding="utf-8") if fehbg.is_file() else None
        return {"backend": "feh", "fehbg": content}

    def apply_snapshot(self, snapshot: dict[str, Any]) -> None:
        content = snapshot.get("fehbg")
        if content:
            proc = subprocess.Popen(
                ["sh", "-c", content],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            proc.wait(timeout=30)
        elif snapshot.get("path"):
            self.set_wallpaper(Path(snapshot["path"]))

    def set_wallpaper(self, path: Path) -> None:
        env = os.environ.copy()
        env.setdefault("DISPLAY", ":0")
        _run(["feh", "--bg-fill", str(path.resolve())], check=True)

    def get_current_wallpaper(self) -> Path | None:
        fehbg = Path.home() / ".fehbg"
        if not fehbg.is_file():
            return None
        text = fehbg.read_text(encoding="utf-8")
        parts = text.split()
        for part in reversed(parts):
            if part.endswith((".jpg", ".jpeg", ".png", ".webp")):
                candidate = Path(part.strip("'\""))
                if candidate.is_file():
                    return candidate
        return None


class SwaybgWallpaperBackend:
    """swaybg child process for Wayland compositors."""

    _process: subprocess.Popen[bytes] | None = None
    _last_path: Path | None = None

    def capture_snapshot(self) -> dict[str, Any]:
        return {
            "backend": "swaybg",
            "path": str(self._last_path) if self._last_path else None,
        }

    def apply_snapshot(self, snapshot: dict[str, Any]) -> None:
        raw = snapshot.get("path")
        if raw:
            self.set_wallpaper(Path(raw))

    def set_wallpaper(self, path: Path) -> None:
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._process.kill()
        resolved = path.resolve()
        self._last_path = resolved
        size = os.environ.get("SWAYBG_SIZE", "1920x1080")
        self._process = subprocess.Popen(
            ["swaybg", "-i", str(resolved), "-m", "fill", "-o", "*", "-s", size],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def get_current_wallpaper(self) -> Path | None:
        return self._last_path


class NitrogenWallpaperBackend:
    """nitrogen --set-zoom-fill."""

    def capture_snapshot(self) -> dict[str, Any]:
        cfg = Path.home() / ".config" / "nitrogen" / "bg-saved.cfg"
        path = None
        if cfg.is_file():
            for line in cfg.read_text(encoding="utf-8").splitlines():
                if line.startswith("file="):
                    candidate = Path(line.split("=", 1)[1].strip())
                    if candidate.is_file():
                        path = candidate
                        break
        return {"backend": "nitrogen", "path": str(path) if path else None}

    def apply_snapshot(self, snapshot: dict[str, Any]) -> None:
        raw = snapshot.get("path")
        if raw:
            self.set_wallpaper(Path(raw))

    def set_wallpaper(self, path: Path) -> None:
        _run(["nitrogen", "--set-zoom-fill", str(path.resolve()), "--save"])

    def get_current_wallpaper(self) -> Path | None:
        snap = self.capture_snapshot()
        raw = snap.get("path")
        return Path(raw) if raw else None


def select_wm_fallback_backend() -> (
    FehWallpaperBackend | SwaybgWallpaperBackend | NitrogenWallpaperBackend
):
    if _which("swaybg"):
        return SwaybgWallpaperBackend()
    if _which("feh"):
        return FehWallpaperBackend()
    if _which("nitrogen"):
        return NitrogenWallpaperBackend()
    raise OSError("No feh, swaybg, or nitrogen found for wallpaper fallback")


Backend = (
    GnomeWallpaperBackend
    | KdeWallpaperBackend
    | FehWallpaperBackend
    | SwaybgWallpaperBackend
    | NitrogenWallpaperBackend
)
