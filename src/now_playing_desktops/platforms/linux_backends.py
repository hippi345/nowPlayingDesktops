"""Linux wallpaper backends (GNOME, KDE, XFCE, feh, swaybg, nitrogen)."""

from __future__ import annotations

import configparser
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import quote

from now_playing_desktops.platforms.linux_screen import list_linux_screens, path_from_file_uri

logger = logging.getLogger(__name__)

_XFCONF_CHANNEL = "xfce4-desktop"
_XFCE_LAST_IMAGE_KEY_RE = re.compile(r"^/backdrop/screen\d+/monitor[^/]+/workspace\d+/last-image$")
_XFCE_IMAGE_STYLE_ZOOMED = "5"

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


class XfceWallpaperBackend:
    """XFCE / xfdesktop via xfconf-query backdrop last-image keys."""

    def __init__(self, *, feh_fallback: FehWallpaperBackend | None = None) -> None:
        self._feh = feh_fallback or FehWallpaperBackend()
        self._delegated_to_feh = False
        self._last_source_path: Path | None = None
        self._refresh_slot = 0

    @staticmethod
    def available() -> bool:
        return _which("xfconf-query") is not None

    def _xfconf_list_properties(self) -> list[str]:
        proc = _run(["xfconf-query", "-c", _XFCONF_CHANNEL, "-l"], check=False)
        if proc.returncode != 0:
            return []
        return [line.strip() for line in proc.stdout.splitlines() if line.strip()]

    def _xfconf_get(self, prop: str) -> str | None:
        proc = _run(
            ["xfconf-query", "-c", _XFCONF_CHANNEL, "-p", prop],
            check=False,
        )
        if proc.returncode != 0:
            return None
        return proc.stdout.strip()

    def _xfconf_set(self, prop: str, value: str, *, create: bool = False) -> bool:
        cmd = ["xfconf-query", "-c", _XFCONF_CHANNEL, "-p", prop, "-s", value]
        if create:
            cmd = [
                "xfconf-query",
                "-c",
                _XFCONF_CHANNEL,
                "-p",
                prop,
                "-n",
                "-t",
                "string",
                "-s",
                value,
            ]
        proc = _run(cmd, check=False)
        return proc.returncode == 0

    def _last_image_keys(self) -> list[str]:
        return [key for key in self._xfconf_list_properties() if _XFCE_LAST_IMAGE_KEY_RE.match(key)]

    @staticmethod
    def _image_style_key(last_image_key: str) -> str:
        parent, _ = last_image_key.rsplit("/", 1)
        return f"{parent}/image-style"

    def _ensure_last_image_keys(self) -> list[str] | None:
        keys = self._last_image_keys()
        if keys:
            return keys
        screens = list_linux_screens()
        created: list[str] = []
        for screen in screens:
            prop = f"/backdrop/screen0/monitor{screen.screen_id}/workspace0/last-image"
            if self._xfconf_set(prop, "", create=True):
                created.append(prop)
        if created:
            return created
        if len(screens) == 1:
            prop = "/backdrop/screen0/monitor0/workspace0/last-image"
            if self._xfconf_set(prop, "", create=True):
                return [prop]
        return None

    def _delegate_to_feh(self, reason: str, path: Path) -> None:
        logger.info(
            "XFCE wallpaper: %s; falling back to feh/swaybg/nitrogen",
            reason,
        )
        self._delegated_to_feh = True
        self._feh.set_wallpaper(path)

    def _effective_wallpaper_path(self, path: Path) -> Path:
        resolved = path.resolve()
        if self._last_source_path == resolved:
            self._refresh_slot ^= 1
            alt = resolved.parent / (
                f"{resolved.stem}.npd-xfce-{self._refresh_slot}{resolved.suffix}"
            )
            shutil.copy2(resolved, alt)
            return alt
        self._last_source_path = resolved
        self._refresh_slot = 0
        return resolved

    def capture_snapshot(self) -> dict[str, Any]:
        if self._delegated_to_feh:
            snap = self._feh.capture_snapshot()
            snap["xfce_delegated_feh"] = True
            return snap
        last_image: dict[str, str] = {}
        image_style: dict[str, str] = {}
        for key in self._last_image_keys():
            value = self._xfconf_get(key)
            if value is not None:
                last_image[key] = value
            style_key = self._image_style_key(key)
            style_value = self._xfconf_get(style_key)
            image_style[style_key] = style_value if style_value is not None else ""
        primary_path = None
        if last_image:
            first = next(iter(last_image.values()))
            primary_path = path_from_file_uri(first) or Path(first)
        return {
            "backend": "xfce",
            "xfconf_last_image": last_image,
            "xfconf_image_style": image_style,
            "path": str(primary_path) if primary_path else None,
        }

    def apply_snapshot(self, snapshot: dict[str, Any]) -> None:
        if snapshot.get("xfce_delegated_feh") or snapshot.get("backend") == "feh":
            self._delegated_to_feh = True
            self._feh.apply_snapshot(snapshot)
            return
        for key, value in (snapshot.get("xfconf_last_image") or {}).items():
            self._xfconf_set(key, value)
        for key, value in (snapshot.get("xfconf_image_style") or {}).items():
            if value == "":
                _run(
                    ["xfconf-query", "-c", _XFCONF_CHANNEL, "-p", key, "-r"],
                    check=False,
                )
            else:
                self._xfconf_set(key, value)

    def set_wallpaper(self, path: Path) -> None:
        if self._delegated_to_feh:
            self._feh.set_wallpaper(path)
            return
        keys = self._ensure_last_image_keys()
        if not keys:
            self._delegate_to_feh(
                "no xfconf backdrop last-image keys and could not create monitor keys",
                path,
            )
            return
        effective = self._effective_wallpaper_path(path)
        image_path = str(effective)
        for key in keys:
            if not self._xfconf_set(key, image_path):
                logger.warning("XFCE wallpaper: failed to set %s", key)
            style_key = self._image_style_key(key)
            current_style = self._xfconf_get(style_key)
            if current_style not in {_XFCE_IMAGE_STYLE_ZOOMED, "5"}:
                self._xfconf_set(style_key, _XFCE_IMAGE_STYLE_ZOOMED, create=True)

    def get_current_wallpaper(self) -> Path | None:
        if self._delegated_to_feh:
            return self._feh.get_current_wallpaper()
        for key in self._last_image_keys():
            raw = self._xfconf_get(key)
            if not raw:
                continue
            candidate = path_from_file_uri(raw) or Path(raw)
            if candidate.is_file():
                return candidate
        return None


class FehWallpaperBackend:
    """feh --bg-fill with restore via ~/.fehbg."""

    def capture_snapshot(self) -> dict[str, Any]:
        fehbg = Path.home() / ".fehbg"
        content = fehbg.read_text(encoding="utf-8") if fehbg.is_file() else None
        return {"backend": "feh", "fehbg": content}

    def apply_snapshot(self, snapshot: dict[str, Any]) -> None:
        content = snapshot.get("fehbg")
        if content:
            env = os.environ.copy()
            env.setdefault("DISPLAY", ":0")
            proc = subprocess.Popen(
                ["sh", "-c", content],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
            )
            proc.wait(timeout=30)
        elif snapshot.get("path"):
            self.set_wallpaper(Path(snapshot["path"]))

    def set_wallpaper(self, path: Path) -> None:
        env = os.environ.copy()
        env.setdefault("DISPLAY", ":0")
        subprocess.run(
            ["feh", "--bg-fill", str(path.resolve())],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )

    def get_current_wallpaper(self) -> Path | None:
        fehbg = Path.home() / ".fehbg"
        if not fehbg.is_file():
            return None
        text = fehbg.read_text(encoding="utf-8")
        parts = text.split()
        for part in reversed(parts):
            cleaned = part.strip().strip("'\"")
            if cleaned.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                candidate = Path(cleaned)
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
    | XfceWallpaperBackend
    | FehWallpaperBackend
    | SwaybgWallpaperBackend
    | NitrogenWallpaperBackend
)
