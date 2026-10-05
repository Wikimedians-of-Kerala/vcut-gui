"""Button icons, from the Material Design Icons set bundled with QtAwesome.

Icons are referred to by a role name — ``"play"``, ``"cut"`` — rather than by
the icon set's own names, so the set can be swapped without touching the
screens. Colours follow the running palette, so the same icons stay legible in
light and dark themes.

QtAwesome is an optional dependency: when it is missing, every lookup returns
an empty icon and the buttons simply show their text, which they always carry
anyway.
"""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtGui import QIcon

#: Role -> Material Design Icons name.
ICON_NAMES: dict[str, str] = {
    # Playback
    "play": "mdi6.play",
    "pause": "mdi6.pause",
    # Double chevrons rather than the numbered "rewind-10" glyphs: the
    # numeral in those is unreadable at button size, and the buttons already
    # carry the amount as text.
    "back10": "mdi6.rewind",
    "forward10": "mdi6.fast-forward",
    "back1": "mdi6.step-backward",
    "forward1": "mdi6.step-forward",
    "go-start": "mdi6.skip-backward",
    "go-end": "mdi6.skip-forward",
    "preview": "mdi6.movie-play-outline",
    "mark-in": "mdi6.contain-start",
    "mark-out": "mdi6.contain-end",
    # Editing the clip list
    "add": "mdi6.plus",
    "remove": "mdi6.delete-outline",
    "duplicate": "mdi6.content-copy",
    "check": "mdi6.check",
    "select-all": "mdi6.check-all",
    "select-none": "mdi6.checkbox-blank-outline",
    "save": "mdi6.content-save-outline",
    # Files and jobs
    "folder": "mdi6.folder-open-outline",
    "licence": "mdi6.license",
    "video": "mdi6.video-outline",
    "csv": "mdi6.file-delimited-outline",
    "cut": "mdi6.content-cut",
    "convert": "mdi6.sync",
    "upload": "mdi6.cloud-upload-outline",
    "description": "mdi6.text-box-outline",
    "schedule": "mdi6.calendar-text",
    "login": "mdi6.login-variant",
    "refresh": "mdi6.refresh",
    "zoom-in": "mdi6.magnify-plus-outline",
    "zoom-out": "mdi6.magnify-minus-outline",
    "zoom-reset": "mdi6.magnify-close",
    "cancel": "mdi6.close-circle-outline",
    "revert": "mdi6.undo",
    # Navigation and chrome
    "back": "mdi6.arrow-left",
    "next": "mdi6.arrow-right",
    "settings": "mdi6.cog-outline",
    "about": "mdi6.information-outline",
}


def available() -> bool:
    """Whether the icon set can be used."""
    try:
        import qtawesome  # noqa: F401  (imported only to test for its presence)
    except ImportError:
        return False
    return True


def _palette_colours() -> tuple[str, str]:
    """Icon colours for the running theme: (normal, disabled)."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return "#404040", "#a0a0a0"
    palette = app.palette()
    return (
        palette.windowText().color().name(),
        palette.color(palette.ColorGroup.Disabled, palette.ColorRole.WindowText).name(),
    )


@lru_cache(maxsize=128)
def _cached(role: str, normal: str, disabled: str) -> QIcon:
    import qtawesome as qta

    name = ICON_NAMES.get(role)
    if not name:
        return QIcon()
    try:
        return qta.icon(name, color=normal, color_disabled=disabled)
    except Exception:  # noqa: BLE001 - a missing glyph must not break the UI
        return QIcon()


def icon(role: str, *, colour: str = "") -> QIcon:
    """The icon for a role, or an empty icon when unavailable.

    Pass ``colour`` to override the palette, for places that need more
    contrast than ordinary button text. The cache is keyed on the colours too,
    so a theme change produces fresh icons rather than serving the previous
    theme's.
    """
    if not available():
        return QIcon()
    normal, disabled = _palette_colours()
    if colour:
        normal = colour
    return _cached(role, normal, disabled)


def apply(button, role: str, *, size: int = 18) -> None:
    """Give a button its icon, leaving the text in place.

    Text is kept because these buttons label actions that are not universally
    recognisable from a glyph alone — "Convert for Commons" is not a picture.

    Qt offers no spacing control between a button's icon and its label, so the
    glyph is drawn inset within a slightly wider pixmap to open up the gap.
    """
    from PySide6.QtCore import QSize

    # Remember how this button was iconed, so a theme change can re-tint it
    # without every call site having to tag it. Relying on callers to do that
    # by hand left nine buttons stuck in the previous theme's colour.
    button.setProperty("iconRole", role)
    button.setProperty("vcutIconSize", size)

    pictogram = icon(role)
    if pictogram.isNull():
        return
    if button.text():
        pictogram = _with_trailing_gap(pictogram, size)
    button.setIcon(pictogram)
    button.setIconSize(QSize(size + (6 if button.text() else 0), size))


def _with_trailing_gap(source: QIcon, size: int, gap: int = 6) -> QIcon:
    """Pad an icon on its right, so it does not touch the button's text."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPainter, QPixmap

    glyph = source.pixmap(size, size)
    if glyph.isNull():
        return source

    ratio = glyph.devicePixelRatio() or 1.0
    canvas = QPixmap(int((size + gap) * ratio), int(size * ratio))
    canvas.setDevicePixelRatio(ratio)
    canvas.fill(Qt.transparent)
    painter = QPainter(canvas)
    painter.drawPixmap(0, 0, glyph)
    painter.end()

    padded = QIcon()
    padded.addPixmap(canvas)
    return padded


def clear_cache() -> None:
    """Drop cached icons, after a theme change."""
    _cached.cache_clear()


def restyle_widget(widget) -> None:
    """Re-tint every icon under ``widget`` for the current theme.

    Walks the widget tree rather than a list of tagged buttons, so an icon
    added later is picked up without anyone remembering to register it.
    """
    from PySide6.QtWidgets import QAbstractButton

    for button in widget.findChildren(QAbstractButton):
        role = button.property("iconRole")
        if not role:
            continue
        size = button.property("vcutIconSize")
        apply(button, role, size=int(size) if size else 18)
