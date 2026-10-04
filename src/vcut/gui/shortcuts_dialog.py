"""The window listing every keyboard shortcut.

Built from the shortcut table rather than written out by hand, so it cannot
describe a binding the application does not have.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .shortcuts import by_group


class KeyLabel(QLabel):
    """A key sequence, drawn like a key."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("keyCap")
        self.setAlignment(Qt.AlignCenter)
        self.setTextInteractionFlags(Qt.TextSelectableByMouse)


class ShortcutsDialog(QDialog):
    """Every shortcut, grouped and searchable."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Keyboard shortcuts")
        self.resize(560, 680)
        self._rows: list[tuple[QWidget, QWidget, str]] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 12)
        layout.setSpacing(10)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search the shortcuts…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        layout.addWidget(self.search)

        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QScrollArea.NoFrame)
        inner = QWidget()
        self.grid = QGridLayout(inner)
        self.grid.setContentsMargins(0, 0, 8, 0)
        self.grid.setHorizontalSpacing(18)
        self.grid.setVerticalSpacing(7)
        self.grid.setColumnStretch(0, 1)

        # Each group keeps a handle on its heading and the rows under it,
        # so searching can hide a whole section when nothing in it matches.
        row = 0
        self._groups: list[tuple[list[QWidget], list[int]]] = []
        for group, shortcuts in by_group().items():
            if row:
                self.grid.setRowMinimumHeight(row, 16)
                row += 1

            heading = QLabel(group)
            heading.setObjectName("screenHeading")
            self.grid.addWidget(heading, row, 0, 1, 2)
            row += 1

            rule = QFrame()
            rule.setObjectName("headingRule")
            rule.setFrameShape(QFrame.HLine)
            self.grid.addWidget(rule, row, 0, 1, 2)
            row += 1

            indices = []
            for shortcut in shortcuts:
                name = QLabel(shortcut.action)
                name.setToolTip(shortcut.description)
                keys = KeyLabel(shortcut.display())
                keys.setToolTip(shortcut.description)
                self.grid.addWidget(name, row, 0)
                self.grid.addWidget(keys, row, 1)
                haystack = (
                    f"{shortcut.action} {shortcut.description} "
                    f"{shortcut.display()} {group}"
                ).lower()
                indices.append(len(self._rows))
                self._rows.append((name, keys, haystack))
                row += 1
            self._groups.append(([heading, rule], indices))

        self.grid.setRowStretch(row, 1)
        area.setWidget(inner)
        layout.addWidget(area, 1)

        self.count = QLabel("")
        self.count.setObjectName("screenSubheading")
        layout.addWidget(self.count)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        buttons.button(QDialogButtonBox.Close).clicked.connect(self.accept)
        layout.addWidget(buttons)

        self._filter("")

    def _filter(self, text: str) -> None:
        """Show only the rows matching what was typed."""
        needle = text.strip().lower()
        shown = 0
        visible_rows: set[int] = set()

        for index, (name, keys, haystack) in enumerate(self._rows):
            match = not needle or needle in haystack
            name.setVisible(match)
            keys.setVisible(match)
            if match:
                shown += 1
                visible_rows.add(index)

        # Hide a group's heading when nothing in it matched.
        for chrome, indices in self._groups:
            any_visible = any(index in visible_rows for index in indices)
            for widget in chrome:
                widget.setVisible(any_visible)

        total = len(self._rows)
        self.count.setText(
            f"{total} shortcuts" if shown == total
            else f"{shown} of {total} shortcuts"
        )
