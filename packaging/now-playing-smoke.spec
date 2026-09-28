# -*- mode: python ; coding: utf-8 -*-
"""Linux-friendly PyInstaller smoke build (catches packaging errors in CI/dev)."""

from PyInstaller.utils.hooks import collect_all

block_cipher = None

pkg_datas, pkg_binaries, pkg_hidden = collect_all("now_playing_desktops")

a = Analysis(
    ["../src/now_playing_desktops/__main__.py"],
    pathex=["../src"],
    binaries=pkg_binaries,
    datas=pkg_datas,
    hiddenimports=list(pkg_hidden),
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
    name="now-playing-smoke",
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
