"""Bundled images.

Paths are resolved relative to this file so they work the same from a source
checkout and from a PyInstaller bundle.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap

LOGO_DIRECTORY = Path(__file__).parent / "logo"
LOGO_FILE = LOGO_DIRECTORY / "vcutcli-logo.svg"

#: Sizes window managers and taskbars commonly ask for.
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


def logo_path() -> str:
    """The logo's path, or an empty string when it is not present."""
    return str(LOGO_FILE) if LOGO_FILE.is_file() else ""


def app_icon() -> QIcon:
    """The application icon, rendered at the usual sizes.

    An SVG loaded straight into a :class:`QIcon` reports no available sizes,
    and some desktops then fall back to a generic icon. Rendering the vector
    into real pixmaps gives them something concrete to choose from. Returns an
    empty icon when the logo is missing, which Qt treats as "no icon" rather
    than an error.
    """
    path = logo_path()
    if not path:
        return QIcon()

    try:
        from PySide6.QtSvg import QSvgRenderer
    except ImportError:  # QtSvg is optional in trimmed-down builds
        return QIcon(path)

    renderer = QSvgRenderer(path)
    if not renderer.isValid():
        return QIcon()

    bounds = renderer.viewBoxF()
    icon = QIcon()
    for size in ICON_SIZES:
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        if bounds.width() and bounds.height():
            # Fit the logo inside the square without distorting it.
            scale = min(size / bounds.width(), size / bounds.height())
            width = bounds.width() * scale
            height = bounds.height() * scale
            renderer.render(
                painter, QRectF((size - width) / 2, (size - height) / 2, width, height)
            )
        else:
            renderer.render(painter)
        painter.end()
        icon.addPixmap(pixmap)
    return icon


def logo_pixmap(size: int = 96) -> QPixmap:
    """The logo at one size, for the About dialog."""
    icon = app_icon()
    return QPixmap() if icon.isNull() else icon.pixmap(size, size)
