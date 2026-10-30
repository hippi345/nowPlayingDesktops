# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for now-playing-macos (run on macos-latest)."""

from PyInstaller.utils.hooks import collect_all

block_cipher = None

pkg_datas, pkg_binaries, pkg_hidden = collect_all("now_playing_desktops")
app_datas, app_binaries, app_hidden = collect_all("appscript")
pkg_datas += app_datas
pkg_binaries += app_binaries
hiddenimports = list(pkg_hidden) + list(app_hidden)

a = Analysis(
    ["pyinstaller_macos_entry.py"],
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
    name="now-playing-macos",
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
