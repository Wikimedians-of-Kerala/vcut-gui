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
        self.list.setAlternatingRowColors(True)
        for licence in LICENCES:
            item = QListWidgetItem(f"{licence.name}\n{licence.note}")
            item.setData(Qt.UserRole, licence.template)
            item.setToolTip(licence.template)
            self.list.addItem(item)
        self.list.itemDoubleClicked.connect(lambda _i: self.accept())
        layout.addWidget(self.list, 1)

        # Select whatever is already in use, so the dialog opens on it.
        normalised = (current or "").strip()
        for row in range(self.list.count()):
            if self.list.item(row).data(Qt.UserRole) == normalised:
                self.list.setCurrentRow(row)
                break
        else:
            self.list.setCurrentRow(0)

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

    def chosen(self) -> str:
        """The selected licence template."""
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item else ""
