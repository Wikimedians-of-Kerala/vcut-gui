"""Application entry point."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from ..settings import AppSettings
from .main_window import MainWindow
from .resources import app_icon
from .theme import Theme, apply_theme


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv)

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
