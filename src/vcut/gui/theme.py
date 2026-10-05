"""Light and dark themes.

The app follows the desktop by default, but the choice can be forced — useful
when the system theme is light and the work is colour-critical video, or when
a desktop reports a theme Qt cannot read. The chosen mode is saved with the
rest of the settings.
"""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette


class Theme(str, Enum):
    SYSTEM = "system"
    LIGHT = "light"
    DARK = "dark"

    @property
    def label(self) -> str:
        return {
            Theme.SYSTEM: "Follow the system",
            Theme.LIGHT: "Light",
            Theme.DARK: "Dark",
        }[self]


#: Colours for the two built-in palettes.
LIGHT = {
    "window": "#f4f5f7", "base": "#ffffff", "alternate": "#eceef1",
    "text": "#1c1f24", "disabled": "#9aa0a6", "button": "#e9ebee",
    "highlight": "#2a6fc9", "highlight_text": "#ffffff",
    "tooltip": "#ffffe1", "tooltip_text": "#1c1f24", "link": "#1a5fb4",
}
DARK = {
    "window": "#1b2029", "base": "#161a21", "alternate": "#20262f",
    "text": "#e6e9ef", "disabled": "#6b7280", "button": "#262d38",
    "highlight": "#4a8fd6", "highlight_text": "#ffffff",
    "tooltip": "#2a313c", "tooltip_text": "#e6e9ef", "link": "#78b7f0",
}


def system_prefers_dark() -> bool:
    """Whether the desktop is using a dark colour scheme."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return False

    # Qt 6.5+ reports the desktop's preference directly.
    hints = app.styleHints()
    scheme = getattr(hints, "colorScheme", None)
    if scheme is not None:
        try:
            return scheme() == Qt.ColorScheme.Dark
        except (AttributeError, TypeError):
            pass

    window = app.palette().window().color()
    brightness = (
        window.red() * 299 + window.green() * 587 + window.blue() * 114
    ) / 1000
    return brightness < 128


def resolve(theme: Theme) -> Theme:
    """Turn ``SYSTEM`` into the theme actually in force."""
    if theme is not Theme.SYSTEM:
        return theme
    return Theme.DARK if system_prefers_dark() else Theme.LIGHT


def build_palette(theme: Theme) -> QPalette:
    """A full palette for one theme."""
    colours = DARK if resolve(theme) is Theme.DARK else LIGHT
    palette = QPalette()

    window = QColor(colours["window"])
    base = QColor(colours["base"])
    text = QColor(colours["text"])
    disabled = QColor(colours["disabled"])
    button = QColor(colours["button"])
    highlight = QColor(colours["highlight"])

    palette.setColor(QPalette.Window, window)
    palette.setColor(QPalette.WindowText, text)
    palette.setColor(QPalette.Base, base)
    palette.setColor(QPalette.AlternateBase, QColor(colours["alternate"]))
    palette.setColor(QPalette.Text, text)
    palette.setColor(QPalette.Button, button)
    palette.setColor(QPalette.ButtonText, text)
    palette.setColor(QPalette.BrightText, QColor("#ff5555"))
    palette.setColor(QPalette.Highlight, highlight)
    palette.setColor(QPalette.HighlightedText, QColor(colours["highlight_text"]))
    palette.setColor(QPalette.ToolTipBase, QColor(colours["tooltip"]))
    palette.setColor(QPalette.ToolTipText, QColor(colours["tooltip_text"]))
    palette.setColor(QPalette.Link, QColor(colours["link"]))

    for role in (
        QPalette.WindowText, QPalette.Text, QPalette.ButtonText,
        QPalette.Highlight, QPalette.HighlightedText,
    ):
        palette.setColor(QPalette.Disabled, role, disabled)

    return palette


def _arrow_icon(colour: str, *, size: int = 10, up: bool = False) -> str:
    """Write a small triangle PNG and return its path, for the combo arrow.

    Styling ``QComboBox::drop-down`` at all stops Qt drawing its own arrow,
    and the usual CSS border-triangle trick renders as a flat bar under
    Fusion. Supplying a real image is the one approach that behaves the same
    everywhere.
    """
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QPainter, QPixmap, QPolygon

    from ..settings import cache_directory

    name = f"arrow-{'up' if up else 'down'}-{colour.lstrip('#')}-{size}.png"
    target = cache_directory() / name
    if target.is_file():
        return target.as_posix()

    width, height = size, size // 2 + 1
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(colour))
    if up:
        points = [QPoint(0, height), QPoint(width, height), QPoint(width // 2, 0)]
    else:
        points = [QPoint(0, 0), QPoint(width, 0), QPoint(width // 2, height)]
    painter.drawPolygon(QPolygon(points))
    painter.end()

    try:
        pixmap.save(str(target), "PNG")
    except OSError:
        return ""
    return target.as_posix()


#: One spacing scale for the whole interface. Mixing ad-hoc numbers per
#: screen is what made the padding look arbitrary: fields were generously
#: padded inside while the gaps between them were Qt's tight default, so the
#: text sat far from its own border but close to everything else.
SPACE_TIGHT = 6      # between tightly-related controls, e.g. a button pair
SPACE_ROW = 12       # between rows of a form
SPACE_GROUP = 18     # between one section and the next
SPACE_EDGE = 18      # from a panel's edge to its content

#: Inside an input: enough to breathe, less than the gap around it.
FIELD_PADDING_V = 4
FIELD_PADDING_H = 9
FIELD_HEIGHT = 30


def stylesheet(theme: Theme) -> str:
    """Spacing and sizing shared by every screen.

    Qt's default form controls are tight enough that a combo box and a line
    edit end up different heights on the same row. Giving them a common
    minimum height and real padding keeps the forms even.
    """
    colours = DARK if resolve(theme) is Theme.DARK else LIGHT
    border = colours["alternate"] if resolve(theme) is Theme.DARK else "#c7ccd4"
    # The column-divider grip: brighter than the grid so it is noticed, but
    # not so bright it competes with the content.
    grip = "#6d7b92" if resolve(theme) is Theme.DARK else "#8b95a4"
    arrow = _arrow_icon(colours["text"])
    arrow_up = _arrow_icon(colours["text"], size=8, up=True)
    arrow_small = _arrow_icon(colours["text"], size=8)
    arrow_rule = f"image: url({arrow});" if arrow else ""
    up_rule = f"image: url({arrow_up});" if arrow_up else ""
    down_rule = f"image: url({arrow_small});" if arrow_small else ""
    return f"""
    QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox, QDateEdit {{
        min-height: {FIELD_HEIGHT}px;
        padding: {FIELD_PADDING_V}px {FIELD_PADDING_H}px;
        border: 1px solid {border};
        border-radius: 4px;
        background: {colours["base"]};
        selection-background-color: {colours["highlight"]};
    }}
    QComboBox:focus, QLineEdit:focus, QSpinBox:focus, QDateEdit:focus {{
        border: 1px solid {colours["highlight"]};
    }}
    QComboBox:disabled, QLineEdit:disabled, QSpinBox:disabled,
    QDateEdit:disabled {{
        color: {colours["disabled"]};
    }}
    /* A tinted panel and a divider, so a combo box is visibly more than a
       text field even before the arrow is noticed. */
    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 28px;
        border-left: 1px solid {border};
        border-top-right-radius: 4px;
        border-bottom-right-radius: 4px;
        background: {colours["button"]};
    }}
    QComboBox::drop-down:hover {{ background: {colours["highlight"]}; }}
    QComboBox::down-arrow {{ {arrow_rule} width: 10px; height: 6px; }}
    QComboBox::down-arrow:disabled {{ opacity: 0.4; }}

    /* The calendar button, given the same panel as a combo box arrow so it
       reads as something to press rather than part of the text. */
    QDateEdit::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 28px;
        border-left: 1px solid {border};
        border-top-right-radius: 4px;
        border-bottom-right-radius: 4px;
        background: {colours["button"]};
    }}
    QDateEdit::drop-down:hover {{ background: {colours["highlight"]}; }}
    QDateEdit::down-arrow {{ {arrow_rule} width: 10px; height: 6px; }}

    /* The calendar itself, which Fusion leaves cramped and hard to read. */
    QCalendarWidget QAbstractItemView {{
        selection-background-color: {colours["highlight"]};
        selection-color: {colours["highlight_text"]};
        outline: none;
    }}
    QCalendarWidget QWidget#qt_calendar_navigationbar {{
        background: {colours["alternate"]};
    }}

    /* Spin boxes get the same treatment: their steppers are otherwise almost
       invisible against a restyled field. */
    QSpinBox::up-button, QDoubleSpinBox::up-button {{
        subcontrol-origin: border;
        subcontrol-position: top right;
        width: 22px;
        border-left: 1px solid {border};
        border-top-right-radius: 4px;
        background: {colours["button"]};
    }}
    QSpinBox::down-button, QDoubleSpinBox::down-button {{
        subcontrol-origin: border;
        subcontrol-position: bottom right;
        width: 22px;
        border-left: 1px solid {border};
        border-top: 1px solid {border};
        border-bottom-right-radius: 4px;
        background: {colours["button"]};
    }}
    QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
    QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
        background: {colours["highlight"]};
    }}
    QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
        {up_rule} width: 8px; height: 5px;
    }}
    QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
        {down_rule} width: 8px; height: 5px;
    }}
    QComboBox QAbstractItemView {{
        padding: 5px;
        /* Dropdown rows are cramped by default. */
        min-height: 30px;
        background: {colours["base"]};
        selection-background-color: {colours["highlight"]};
    }}
    /* #transportButton and #stepButton override this below: Qt merges a bare
       QPushButton rule into theirs, so each must restate what it needs. */
    QPushButton {{
        min-height: {FIELD_HEIGHT}px;
        padding: {FIELD_PADDING_V}px 16px;
        border: 1px solid {border};
        border-radius: 5px;
        background: {colours["button"]};
        /* Separates the icon from its label; Qt packs them together. */
        icon-size: 18px;
    }}
    QPushButton:hover {{ border: 1px solid {colours["highlight"]}; }}
    QPushButton:disabled {{ color: {colours["disabled"]}; }}
    QPushButton#transportButton {{
        min-height: 0;
        min-width: 0;
        padding: 0;
        border: none;
        background: transparent;
    }}
    QPushButton#transportButton:hover {{ border: none; }}
    /* The marking buttons sit inside the transport, so they are smaller than
       a normal button and carry no heavy border. */
    QPushButton#markButton {{
        min-height: 30px;
        padding: 5px 12px;
        border: 1px solid {border};
        border-radius: 5px;
    }}
    /* Each section is a card: a filled panel with its title sitting on the
       border, so the groups on the setup screen are clearly separate. */
    QGroupBox {{
        margin-top: 16px;
        padding: {SPACE_EDGE + 6}px {SPACE_EDGE}px {SPACE_EDGE}px {SPACE_EDGE}px;
        border: 1px solid {border};
        border-radius: 8px;
        background: {colours["alternate"]};
        font-weight: bold;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 14px;
        padding: 3px 9px;
        border: 1px solid {border};
        border-radius: 5px;
        background: {colours["highlight"]};
        color: {colours["highlight_text"]};
    }}
    QTableWidget {{
        gridline-color: {border};
        selection-background-color: {colours["highlight"]};
    }}
    QTableWidget::item {{ padding: 6px 8px; }}

    /* Rows in a plain list, which Fusion packs tightly. The licence picker
       carries a name and an explanation in each row, so it needs the room
       more than most. */
    QListWidget {{
        border: 1px solid {border};
        border-radius: 4px;
        background: {colours["base"]};
        outline: none;
    }}
    QListWidget::item {{
        padding: {SPACE_TIGHT}px {SPACE_ROW}px;
        border-bottom: 1px solid {border};
    }}
    QListWidget::item:selected {{
        background: {colours["highlight"]};
        color: {colours["highlight_text"]};
    }}
    /* A row built from labels needs its colours stated outright. Without
       the first rule the text inherits nothing and vanishes on a light
       background; without the second, the muted explanation stays grey on
       the selection and becomes unreadable. */
    QListWidget QLabel {{
        color: {colours["text"]};
        background: transparent;
    }}
    QListWidget QLabel#screenSubheading {{
        color: {colours["disabled"]};
        background: transparent;
    }}
    QListWidget::item:selected QLabel,
    QListWidget::item:selected QLabel#screenSubheading {{
        color: {colours["highlight_text"]};
    }}
    QListWidget::item:hover:!selected {{
        background: {colours["alternate"]};
    }}
    /* A visible grip on the divider, so it reads as draggable. The right
       border is drawn thicker and lighter than the grid lines. */
    QHeaderView::section:horizontal {{
        padding: 8px 10px;
        border: none;
        /* An inset pair of lines reads as a grip rather than a plain rule,
           so it is clear the divider can be dragged. */
        border-right: 3px double {grip};
        border-bottom: 1px solid {border};
        background: {colours["button"]};
        font-weight: bold;
    }}
    QHeaderView::section:horizontal:hover {{
        background: {colours["alternate"]};
        border-right: 3px double {colours["highlight"]};
    }}
    QHeaderView::section:horizontal:last {{
        border-right: none;
    }}
    QHeaderView::section:vertical {{
        padding: 4px;
        border: none;
        border-bottom: 1px solid {border};
        background: {colours["button"]};
    }}
    QProgressBar {{
        min-height: 22px;
        border: 1px solid {border};
        border-radius: 4px;
        text-align: center;
    }}
    QProgressBar::chunk {{ background: {colours["highlight"]}; border-radius: 3px; }}
    QCheckBox {{ spacing: 7px; padding: 2px 0; }}
    QCheckBox::indicator {{ width: 15px; height: 15px; }}
    QPlainTextEdit {{
        border: 1px solid {border};
        border-radius: 4px;
        padding: 4px;
    }}

    /* The wizard step bar. The current step is filled with the highlight
       colour so there is never a question about where you are. */
    QPushButton#stepButton {{
        min-height: 34px;
        padding: 8px 18px;
        border: 1px solid transparent;
        border-radius: 6px;
        background: transparent;
        color: {colours["disabled"]};
        font-weight: normal;
        text-align: left;
    }}
    QPushButton#stepButton:hover {{
        background: {colours["button"]};
        color: {colours["text"]};
    }}
    QPushButton#stepButton[done="true"] {{
        color: {colours["text"]};
    }}
    QPushButton#stepButton[current="true"] {{
        background: {colours["highlight"]};
        color: {colours["highlight_text"]};
        font-weight: bold;
    }}
    /* The heading is a banner, with a coloured bar down its leading edge,
       so the current step is obvious without reading anything. */
    QFrame#screenHeadingPanel {{
        background: {colours["alternate"]};
        border: 1px solid {border};
        border-left: 5px solid {colours["highlight"]};
        border-radius: 6px;
    }}
    QLabel#screenStepNumber {{
        background: {colours["highlight"]};
        color: {colours["highlight_text"]};
        border-radius: 15px;
        font-size: 15px;
        font-weight: bold;
        min-width: 30px;
        max-width: 30px;
        min-height: 30px;
        max-height: 30px;
    }}
    /* Key sequences in the shortcuts window, drawn like keys. */
    QLabel#keyCap {{
        background: {colours["button"]};
        color: {colours["text"]};
        border: 1px solid {border};
        border-bottom: 2px solid {border};
        border-radius: 5px;
        padding: 3px 9px;
        font-family: monospace;
        font-size: 11px;
    }}
    /* Stands in for the video while encoding, when the player has let go
       of the file. Grey rather than black, so it reads as "deliberately
       empty" instead of "the picture failed". */
    QLabel#videoPlaceholder {{
        background: {colours["alternate"]};
        color: {colours["disabled"]};
        border: 1px solid {border};
        border-radius: 6px;
        font-size: 12px;
    }}
    QLabel#screenHeading {{
        font-size: 18px;
        font-weight: bold;
        color: {colours["text"]};
    }}
    QLabel#screenSubheading {{
        color: {colours["disabled"]};
    }}
    """


def apply_theme(theme: Theme) -> Theme:
    """Apply a theme to the running application; returns what was resolved."""
    from PySide6.QtWidgets import QApplication

    from . import icons

    app = QApplication.instance()
    resolved = resolve(theme)
    if app is None:
        return resolved

    # Fusion looks the same on every platform, so the palettes below behave
    # predictably rather than fighting a native style's own colours.
    app.setStyle("Fusion")
    app.setPalette(build_palette(theme))
    app.setStyleSheet(stylesheet(theme))

    # Icons are tinted when built, so the cache must go when colours change.
    icons.clear_cache()
    return resolved
