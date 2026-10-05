"""Application entry point."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from ..settings import AppSettings
from .main_window import MainWindow
from .resources import app_icon
from .theme import Theme, apply_theme


def _decode_in_software() -> None:
    """Stop Qt trying to decode video on the GPU.

    Qt Multimedia reaches for VAAPI first and does not fall back when the
    hardware cannot manage a codec. A GPU without AV1 decoding -- which is
    most of them -- then produces a black window and a run of errors:

        No support for codec av1 profile 0.
        Failed setup for format vaapi: hwaccel initialisation returned error.
        Your platform doesn't support hardware accelerated AV1 decoding.

    AV1 is the format this program recommends for Commons, so the clips it
    produces are exactly the ones that fail. Software decoding plays them
    without complaint, and a conference talk at 720p costs little to decode.

    This is playback only. Encoding keeps whatever hardware setting the
    FFmpeg window holds, where the GPU does earn its place.
    """
    import os

    os.environ.setdefault("QT_FFMPEG_DECODING_HW_DEVICE_TYPES", "")


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv)

    # Before QApplication: Qt reads this when its multimedia backend starts.
    _decode_in_software()

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
