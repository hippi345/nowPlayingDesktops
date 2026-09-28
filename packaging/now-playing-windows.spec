# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for now-playing-windows.exe (run on windows-latest)."""

from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

pkg_datas, pkg_binaries, pkg_hidden = collect_all("now_playing_desktops")
hiddenimports = list(pkg_hidden) + collect_submodules("winrt")

a = Analysis(
    ["pyinstaller_win_entry.py"],
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
    name="now-playing-windows",
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
