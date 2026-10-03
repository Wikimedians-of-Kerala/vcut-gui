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


def stylesheet(theme: Theme) -> str:
    """Spacing and sizing shared by every screen.

    Qt's default form controls are tight enough that a combo box and a line
    edit end up different heights on the same row. Giving them a common
    minimum height and real padding keeps the forms even.
    """
    colours = DARK if resolve(theme) is Theme.DARK else LIGHT
    border = colours["alternate"] if resolve(theme) is Theme.DARK else "#c7ccd4"
    return f"""
    QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox {{
        min-height: 30px;
        padding: 7px 11px;
        border: 1px solid {border};
        border-radius: 4px;
        background: {colours["base"]};
        selection-background-color: {colours["highlight"]};
    }}
    QComboBox:focus, QLineEdit:focus, QSpinBox:focus {{
        border: 1px solid {colours["highlight"]};
    }}
    QComboBox:disabled, QLineEdit:disabled, QSpinBox:disabled {{
        color: {colours["disabled"]};
    }}
    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: center right;
        width: 26px;
        border: none;
        /* The arrow itself is left to the style: overriding it with a CSS
           border triangle renders as a flat bar on Fusion. */
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
        min-height: 32px;
        padding: 9px 20px;
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
    /* Each section is a card: a filled panel with its title sitting on the
       border, so the groups on the setup screen are clearly separate. */
    QGroupBox {{
        margin-top: 16px;
        padding: 18px 14px 14px 14px;
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
    QHeaderView::section {{
        padding: 8px 6px;
        border: none;
        border-right: 1px solid {border};
        border-bottom: 1px solid {border};
        background: {colours["button"]};
        font-weight: bold;
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
