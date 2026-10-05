"""Application entry point."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from ..settings import AppSettings
from .main_window import MainWindow
from .resources import app_icon
from .theme import Theme, apply_theme


def _embed_video_under_x11() -> None:
    """Run Qt through XWayland so libmpv can render inside the window.

    libmpv embeds by being handed a native window id, which is an X11
    mechanism. On a Wayland session there is no such id to give, so mpv
    opens a window of its own: the video appears in a separate "mpv"
    window instead of in the player pane.

    XWayland is present on every Wayland desktop that runs X11 programs,
    so asking Qt for the xcb platform costs nothing and keeps the video
    where it belongs. Only done when libmpv is actually in use; with Qt's
    own player there is nothing to embed and the native session is better.

    Set before QApplication, which reads the platform at startup.
    """
    import os

    if os.environ.get("QT_QPA_PLATFORM"):
        return  # the user chose; leave it alone
    if not os.environ.get("WAYLAND_DISPLAY"):
        return  # not a Wayland session
    if not os.environ.get("DISPLAY"):
        return  # no XWayland to fall back to

    from .mpv_player import available as mpv_available

    if mpv_available():
        os.environ["QT_QPA_PLATFORM"] = "xcb"


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv)

    _embed_video_under_x11()

    # Used by the packaging scripts to prove a built bundle actually starts:
    # entry-point and missing-import faults only surface at runtime.
    self_test = "--self-test" in argv
    if self_test:
        argv.remove("--self-test")

    app = QApplication(argv)
    app.setApplicationName("vcut")
    app.setApplicationDisplayName("vcut")
    app.setOrganizationName("vcut")
    app.setWindowIcon(app_icon())
    # Wayland takes the taskbar icon from the desktop file name, not the window.
    app.setDesktopFileName("vcut-gui")

    settings = AppSettings.load()
    try:
        apply_theme(Theme(settings.theme))
    except ValueError:
        apply_theme(Theme.SYSTEM)

    window = MainWindow(settings)
    if self_test:
        from .. import __version__

        for index in range(4):
            window.go_to(index)
        print(f"vcut {__version__}: started, {window.stack.count()} screens")
        return 0

    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
