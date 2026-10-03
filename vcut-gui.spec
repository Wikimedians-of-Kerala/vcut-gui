# PyInstaller build file. Produces a one-folder application.
#
#     uv pip install pyinstaller
#     pyinstaller vcut-gui.spec
#
# FFmpeg is NOT bundled: it is large, and its licensing depends on how it was
# built. The app looks for ffmpeg on PATH and explains how to install it when
# it is missing. To ship it anyway, drop ffmpeg(.exe) and ffprobe(.exe) beside
# the built executable and they will be found first.

import sys

block_cipher = None

a = Analysis(
    ["src/vcut/gui/app.py"],
    pathex=["src"],
    binaries=[],
    datas=[("src/vcut/gui/logo", "vcut/gui/logo")],
    hiddenimports=[
        "vcut.gui.screen_setup",
        "vcut.gui.screen_verify",
        "vcut.gui.screen_metadata",
        "vcut.gui.screen_upload",
    ],
    hookspath=[],
    runtime_hooks=[],
    # Pywikibot is optional: leaving it out keeps the build small, and the
    # upload screen explains how to install it.
    excludes=["tkinter", "matplotlib", "numpy", "PySide6.QtWebEngineCore"],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="vcut-gui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # a GUI app should not open a terminal
    disable_windowed_traceback=False,
    icon=None,   # see packaging/README.md for making .ico / .icns files
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="vcut-gui",
)
