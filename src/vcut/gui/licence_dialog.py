"""Choosing a licence for Commons.

The licence is a wikitext template, and typing one from memory is how a
typo reaches a hundred files at once. These are the ones a conference
recording actually uses, each verified to exist on Commons.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .theme import SPACE_EDGE, SPACE_ROW, SPACE_TIGHT


@dataclass(frozen=True)
class Licence:
    """One licence offered in the picker."""

    template: str
    name: str
    note: str


#: Every template here was checked against Commons. The order is the order a
#: conference team is likely to want: the Wikimedia default first, then the
#: freer options, then public domain.
LICENCES: tuple[Licence, ...] = (
    Licence(
        "{{Cc-by-sa-4.0}}", "CC BY-SA 4.0",
        "Attribution, and anything built on it shares alike. The usual "
        "choice for Wikimedia events, and what Commons assumes.",
    ),
    Licence(
        "{{Cc-by-4.0}}", "CC BY 4.0",
        "Attribution only. Freer than BY-SA: reusers need not share alike.",
    ),
    Licence(
        "{{Cc-zero}}", "CC0",
        "No rights reserved. Anyone may use it for anything, without credit.",
    ),
    Licence(
        "{{Cc-by-sa-3.0}}", "CC BY-SA 3.0",
        "The older share-alike licence. Use 4.0 unless something requires "
        "this one.",
    ),
    Licence(
        "{{Cc-by-3.0}}", "CC BY 3.0",
        "The older attribution licence. Use 4.0 unless the material was "
        "already released under this one.",
    ),
    Licence(
        "{{PD-self}}", "Public domain",
        "You are the copyright holder and release all rights. Only valid "
        "if the recording is genuinely yours to release.",
    ),
)


class LicenceDialog(QDialog):
    """Pick a licence, or see what the current one means."""

    def __init__(self, current: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Choose a licence")
        self.resize(520, 440)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_EDGE, SPACE_ROW, SPACE_EDGE, SPACE_TIGHT)
        layout.setSpacing(SPACE_ROW)

        intro = QLabel(
            "The licence applies to every clip. A conference recording is "
            "usually released under the same terms as the event itself — "
            "check what the speakers agreed to."
        )
        intro.setWordWrap(True)
        intro.setObjectName("screenSubheading")
        layout.addWidget(intro)

        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.list.setSpacing(2)
        # Rows are two lines of different weight, so a widget per row beats
        # a newline in the text: the name can be bold and the explanation
        # can wrap instead of running off the right edge.
        for licence in LICENCES:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, licence.template)
            item.setToolTip(licence.template)
            self.list.addItem(item)

            row = QWidget()
            lines = QVBoxLayout(row)
            lines.setContentsMargins(SPACE_TIGHT, SPACE_TIGHT,
                                     SPACE_TIGHT, SPACE_TIGHT)
            lines.setSpacing(2)

            # Colours are set here rather than in the stylesheet: a label
            # inside an item widget is not reached by QListWidget::item
            # rules, and inherits nothing, so it renders invisible on a
            # light background.
            palette = self.palette()
            text = palette.text().color().name()
            muted = palette.placeholderText().color().name()

            name = QLabel(licence.name)
            name_font = name.font()
            name_font.setBold(True)
            name.setFont(name_font)
            name.setStyleSheet(f"color: {text}; background: transparent;")
            lines.addWidget(name)

            note = QLabel(licence.note)
            note.setWordWrap(True)
            note.setStyleSheet(f"color: {muted}; background: transparent;")
            lines.addWidget(note)

            self.list.setItemWidget(item, row)
            item.setSizeHint(row.sizeHint())

        self.list.itemDoubleClicked.connect(lambda _i: self.accept())
        self.list.currentRowChanged.connect(self._recolour)
        layout.addWidget(self.list, 1)

        # Select whatever is already in use, so the dialog opens on it.
        normalised = (current or "").strip()
        for row in range(self.list.count()):
            if self.list.item(row).data(Qt.UserRole) == normalised:
                self.list.setCurrentRow(row)
                break
        else:
            self.list.setCurrentRow(0)
        self._recolour()

        self.note = QLabel(
            "A licence not listed here can still be typed into the box — "
            "an event-specific permission template, for instance."
        )
        self.note.setWordWrap(True)
        self.note.setObjectName("screenSubheading")
        layout.addWidget(self.note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _recolour(self) -> None:
        """Keep the selected row's text legible against the highlight.

        The labels carry explicit colours, which a selection would not
        otherwise override, leaving muted grey on a strong blue.
        """
        palette = self.palette()
        normal = palette.text().color().name()
        muted = palette.placeholderText().color().name()
        selected = palette.highlightedText().color().name()

        current = self.list.currentRow()
        for row in range(self.list.count()):
            widget = self.list.itemWidget(self.list.item(row))
            if widget is None:
                continue
            labels = widget.findChildren(QLabel)
            if len(labels) != 2:
                continue
            name, note = labels
            if row == current:
                name.setStyleSheet(f"color: {selected}; background: transparent;")
                note.setStyleSheet(f"color: {selected}; background: transparent;")
            else:
                name.setStyleSheet(f"color: {normal}; background: transparent;")
                note.setStyleSheet(f"color: {muted}; background: transparent;")

    def chosen(self) -> str:
        """The selected licence template."""
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item else ""
