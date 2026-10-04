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
    # Not src/vcut/gui/app.py directly: PyInstaller runs its entry script as
    # a top-level module, which breaks that file's relative imports.
    ["packaging/entry.py"],
    pathex=["src"],
    binaries=[],
    datas=[("src/vcut/gui/logo", "vcut/gui/logo")],
    hiddenimports=[
        "vcut",
        "vcut.gui",
        "vcut.gui.app",
        "vcut.gui.screen_setup",
        "vcut.gui.screen_verify",
        "vcut.gui.screen_metadata",
        "vcut.gui.screen_upload",
    ],
    hookspath=[],
    runtime_hooks=[],
    # Pywikibot is optional: leaving it out keeps the build small, and the
    # upload screen explains how to install it.
    #
    # Qt WebEngine is an embedded Chromium: around 150 MB, several times the
    # rest of the bundle. Excluding QtWebEngineCore alone is not enough --
    # its hook stops collecting Chromium's .pak resources while the shared
    # libraries still arrive as transitive dependencies, leaving a build that
    # carries the weight and reports the browser as available but cannot
    # actually start it. Both modules have to go, and the stragglers are
    # pruned below. Browser sign-in is then unavailable in packaged builds,
    # which the login window says; bot passwords work for every account.
    excludes=[
        "tkinter",
        "matplotlib",
        "numpy",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineQuick",
    ],
    cipher=block_cipher,
    noarchive=False,
)

# PyInstaller still pulls the WebEngine shared libraries in behind the
# excludes, as dependencies of Qt libraries that are genuinely needed. They
# are useless without Chromium's resource files, so drop them by name.
_WEBENGINE = ("qtwebengine", "qt6webengine")


def _is_webengine(entry) -> bool:
    name = entry[0].lower()
    return any(marker in name for marker in _WEBENGINE)


a.binaries = TOC([entry for entry in a.binaries if not _is_webengine(entry)])
a.datas = TOC([entry for entry in a.datas if not _is_webengine(entry)])

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
