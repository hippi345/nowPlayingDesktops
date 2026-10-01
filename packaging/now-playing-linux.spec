# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for now-playing-linux (run on ubuntu-latest)."""

from PyInstaller.utils.hooks import collect_all

block_cipher = None

pkg_datas, pkg_binaries, pkg_hidden = collect_all("now_playing_desktops")
dbus_datas, dbus_binaries, dbus_hidden = collect_all("dbus_next")
pkg_datas += dbus_datas
pkg_binaries += dbus_binaries
hiddenimports = list(pkg_hidden) + list(dbus_hidden)

a = Analysis(
    ["pyinstaller_linux_entry.py"],
    pathex=["../src"],
    binaries=pkg_binaries,
    datas=pkg_datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="now-playing-linux",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
