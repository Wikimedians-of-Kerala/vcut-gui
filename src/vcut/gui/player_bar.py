"""The transport bar under the video.

Laid out like a media player rather than a form: a slim scrubber across the
top, then round icon-only buttons centred beneath it, with play given more
weight than the rest. The whole thing sits on a rounded panel so it reads as
one control surface.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from . import icons
from .widgets import is_dark_theme


class RoundButton(QPushButton):
    """A circular icon-only button."""

    def __init__(self, role: str, tooltip: str, *, diameter: int = 40,
                 icon_size: int = 26, primary: bool = False,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("transportButton")
        self.setAutoDefault(False)
        self.setToolTip(tooltip)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(diameter, diameter)
        self.setIconSize(QSize(icon_size, icon_size))
        self._primary = primary
        self._diameter = diameter
        self._role = role
        self.set_role(role)
        self._restyle()

    def set_role(self, role: str) -> None:
        self._role = role
        self.refresh_icon()

    def refresh_icon(self) -> None:
        """Rebuild the icon in the current theme's colour.

        Icons are tinted when they are created, so one made before the widget
        was shown can carry the wrong colour. Rebuilding on restyle keeps them
        matched to the palette actually in use.
        """
        pictogram = icons.icon(self._role, colour=self._icon_colour())
        if not pictogram.isNull():
            self.setIcon(pictogram)
            self.setText("")
        else:
            # No icon set available: fall back to a text glyph so the button
            # is still identifiable.
            self.setText(_FALLBACK_GLYPHS.get(self._role, ""))

    def _icon_colour(self) -> str:
        # Transport glyphs want more contrast than ordinary button text.
        return "#f2f4f8" if is_dark_theme() else "#1c1f24"

    def _restyle(self) -> None:
        self.refresh_icon()
        dark = is_dark_theme()
        radius = self._diameter // 2
        if self._primary:
            background = "rgba(255,255,255,0.20)" if dark else "rgba(0,0,0,0.13)"
            hover = "rgba(255,255,255,0.32)" if dark else "rgba(0,0,0,0.21)"
        else:
            background = "transparent"
            hover = "rgba(255,255,255,0.14)" if dark else "rgba(0,0,0,0.09)"
        pressed = "rgba(255,255,255,0.30)" if dark else "rgba(0,0,0,0.20)"
        self.setStyleSheet(
            f"""
            QPushButton#transportButton {{
                border: none;
                border-radius: {radius}px;
                background: {background};
                font-size: 15px;
                padding: 0px;
                margin: 0px;
                min-height: {self._diameter}px;
                max-height: {self._diameter}px;
                min-width: {self._diameter}px;
                max-width: {self._diameter}px;
            }}
            QPushButton#transportButton:hover {{
                background: {hover};
                border: none;
            }}
            QPushButton#transportButton:pressed {{ background: {pressed}; }}
            QPushButton#transportButton:disabled {{ background: transparent; }}
            """
        )


#: Used only when the icon set is unavailable.
_FALLBACK_GLYPHS = {
    "play": "▶", "pause": "❚❚", "back10": "◀◀", "forward10": "▶▶",
    "back1": "◀|", "forward1": "|▶", "go-start": "|◀", "go-end": "▶|",
    "preview": "⦿",
}


class PlayerBar(QFrame):
    """Scrubber plus transport controls, as one rounded panel."""

    play_toggled = Signal()
    nudged = Signal(int)          # milliseconds, signed
    go_to_start = Signal()
    go_to_end = Signal()
    preview_requested = Signal()
    scrubbed = Signal(int)        # milliseconds
    seek_requested = Signal(float)   # seconds, from the jump box

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("playerBar")
        # A QFrame ignores a stylesheet background unless it is told to paint
        # one, which is what makes the rounded panel show up at all.
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._build()
        self.restyle()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        # -- scrubber, with the times either side -------------------------
        scrub_row = QHBoxLayout()
        scrub_row.setSpacing(10)

        self.position_label = QLabel("00:00:00")
        self.position_label.setObjectName("playerTime")
        self.position_label.setMinimumWidth(66)
        self.position_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        scrub_row.addWidget(self.position_label)

        self.scrubber = QSlider(Qt.Horizontal)
        self.scrubber.setObjectName("playerScrubber")
        self.scrubber.setRange(0, 0)
        self.scrubber.sliderMoved.connect(self.scrubbed)
        self.scrubber.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        scrub_row.addWidget(self.scrubber, 1)

        self.duration_label = QLabel("00:00:00")
        self.duration_label.setObjectName("playerTime")
        self.duration_label.setMinimumWidth(66)
        self.duration_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.duration_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        scrub_row.addWidget(self.duration_label)
        layout.addLayout(scrub_row)

        # -- transport, centred -------------------------------------------
        controls = QHBoxLayout()
        controls.setSpacing(6)
        controls.addStretch(1)

        self.start_button = RoundButton("go-start", "Jump to this clip's start")
        self.start_button.clicked.connect(self.go_to_start)
        controls.addWidget(self.start_button)

        self.back10_button = RoundButton("back10", "Back 10 seconds")
        self.back10_button.clicked.connect(lambda: self.nudged.emit(-10_000))
        controls.addWidget(self.back10_button)

        self.back1_button = RoundButton("back1", "Back 1 second")
        self.back1_button.clicked.connect(lambda: self.nudged.emit(-1000))
        controls.addWidget(self.back1_button)

        # Play is the one control that should be obvious at a glance.
        self.play_button = RoundButton(
            "play", "Play or pause", diameter=52, icon_size=30, primary=True
        )
        self.play_button.clicked.connect(self.play_toggled)
        controls.addSpacing(8)
        controls.addWidget(self.play_button)
        controls.addSpacing(8)

        self.forward1_button = RoundButton("forward1", "Forward 1 second")
        self.forward1_button.clicked.connect(lambda: self.nudged.emit(1000))
        controls.addWidget(self.forward1_button)

        self.forward10_button = RoundButton("forward10", "Forward 10 seconds")
        self.forward10_button.clicked.connect(lambda: self.nudged.emit(10_000))
        controls.addWidget(self.forward10_button)

        self.end_button = RoundButton("go-end", "Jump to this clip's end")
        self.end_button.clicked.connect(self.go_to_end)
        controls.addWidget(self.end_button)

        controls.addSpacing(10)
        self.preview_button = RoundButton(
            "preview", "Play the first few seconds of this clip"
        )
        self.preview_button.clicked.connect(self.preview_requested)
        controls.addWidget(self.preview_button)

        controls.addStretch(1)

        # Typing a timecode is often quicker than scrubbing to it, especially
        # when checking a cut point copied from somewhere else.
        jump_label = QLabel("Go to")
        jump_label.setObjectName("playerTime")
        controls.addWidget(jump_label)

        self.jump_field = QLineEdit()
        self.jump_field.setObjectName("playerJump")
        self.jump_field.setPlaceholderText("00:00:00")
        self.jump_field.setFixedWidth(84)
        self.jump_field.setAlignment(Qt.AlignCenter)
        self.jump_field.setToolTip(
            "Type a timecode and press Enter to jump there (HH:MM:SS)"
        )
        self.jump_field.returnPressed.connect(self._jump)
        controls.addWidget(self.jump_field)

        layout.addLayout(controls)

    def _jump(self) -> None:
        """Seek to the timecode typed into the jump box."""
        from ..models import TimecodeError, parse_timecode

        text = self.jump_field.text().strip()
        if not text:
            return
        try:
            seconds = parse_timecode(text)
        except TimecodeError:
            self.jump_field.setStyleSheet("QLineEdit { border: 1px solid #d34; }")
            self.jump_field.setToolTip(f"{text!r} is not a timecode — use HH:MM:SS")
            return

        maximum = self.scrubber.maximum() / 1000
        if maximum and seconds > maximum:
            self.jump_field.setStyleSheet("QLineEdit { border: 1px solid #d34; }")
            self.jump_field.setToolTip("That is past the end of the video")
            return

        self.jump_field.setStyleSheet("")
        self.jump_field.setToolTip(
            "Type a timecode and press Enter to jump there (HH:MM:SS)"
        )
        self.seek_requested.emit(seconds)

    # -- appearance --------------------------------------------------------

    def restyle(self) -> None:
        """Re-colour for the running theme.

        Colours are solid rather than translucent: a panel defined with alpha
        composites against whatever happens to be behind it, which makes it
        vanish on some backgrounds and in screenshots.
        """
        dark = is_dark_theme()
        if dark:
            panel, groove = "#232a35", "#3a434f"
            filled, handle = "#5a9fe8", "#ffffff"
            text, field = "#c7cedb", "#161a21"
        else:
            panel, groove = "#e4e7ec", "#c2c8d0"
            filled, handle = "#2a6fc9", "#ffffff"
            text, field = "#424953", "#ffffff"

        self.setStyleSheet(
            f"""
            QFrame#playerBar {{
                background: {panel};
                border-radius: 14px;
            }}
            QLabel#playerTime {{
                color: {text};
                font-family: monospace;
                font-size: 11px;
            }}
            QSlider#playerScrubber::groove:horizontal {{
                height: 6px;
                border-radius: 3px;
                background: {groove};
            }}
            QSlider#playerScrubber::sub-page:horizontal {{
                height: 6px;
                border-radius: 3px;
                background: {filled};
            }}
            QSlider#playerScrubber::handle:horizontal {{
                width: 18px;
                height: 18px;
                margin: -6px 0;
                border-radius: 9px;
                background: {handle};
                border: 2px solid {filled};
            }}
            QSlider#playerScrubber::handle:horizontal:hover {{
                background: {filled};
            }}
            QLineEdit#playerJump {{
                background: {field};
                color: {text};
                border: 1px solid {groove};
                border-radius: 5px;
                padding: 3px;
                font-family: monospace;
                font-size: 11px;
            }}
            QLineEdit#playerJump:focus {{ border: 1px solid {filled}; }}
            """
        )
        for button in self.findChildren(RoundButton):
            button._restyle()

    # -- state -------------------------------------------------------------

    def set_playing(self, playing: bool) -> None:
        self.play_button.set_role("pause" if playing else "play")

    def set_position(self, milliseconds: int) -> None:
        if not self.scrubber.isSliderDown():
            self.scrubber.setValue(milliseconds)
        self.position_label.setText(_format(milliseconds))

    def set_duration(self, milliseconds: int) -> None:
        self.scrubber.setRange(0, max(0, milliseconds))
        self.duration_label.setText(_format(milliseconds))

    def set_enabled(self, enabled: bool) -> None:
        self.scrubber.setEnabled(enabled)
        for button in self.findChildren(RoundButton):
            button.setEnabled(enabled)


def _format(milliseconds: int) -> str:
    from ..models import format_timecode

    return format_timecode(max(0, milliseconds) / 1000)
