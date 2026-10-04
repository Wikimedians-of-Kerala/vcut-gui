"""The help window: how to use the program.

A list of topics on the left, the chosen one on the right. The window opens
on the topic for whichever screen you are looking at, since that is nearly
always what you wanted to know about.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .help_content import TOPICS, Topic, for_screen
from .theme import SPACE_EDGE, SPACE_ROW, SPACE_TIGHT


class HelpDialog(QDialog):
    """How to use the program, by topic."""

    def __init__(self, parent: QWidget | None = None, *, screen: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("How to use vcut")
        self.resize(880, 660)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_EDGE, SPACE_ROW, SPACE_EDGE, SPACE_TIGHT)
        layout.setSpacing(SPACE_ROW)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        splitter.addWidget(self._build_sidebar())
        splitter.addWidget(self._build_page())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([250, 630])
        layout.addWidget(splitter, 1)

        footer = QHBoxLayout()
        footer.setSpacing(SPACE_TIGHT)

        self.shortcuts_button = QPushButton("Keyboard shortcuts…")
        self.shortcuts_button.setAutoDefault(False)
        self.shortcuts_button.clicked.connect(self._show_shortcuts)
        footer.addWidget(self.shortcuts_button)
        footer.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.Close).clicked.connect(self.accept)
        footer.addWidget(buttons)
        layout.addLayout(footer)

        # Open on the topic for the screen behind the window: someone asking
        # for help while on the verify screen is asking about that screen.
        wanted = for_screen(screen) if screen else None
        self.show_topic(wanted or TOPICS[0])

    # -- construction ------------------------------------------------------

    def _build_sidebar(self) -> QWidget:
        side = QWidget()
        column = QVBoxLayout(side)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(SPACE_TIGHT)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search the help…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        column.addWidget(self.search)

        self.topics = QListWidget()
        self.topics.setAlternatingRowColors(True)
        for topic in TOPICS:
            item = QListWidgetItem(topic.title)
            item.setData(Qt.UserRole, topic.key)
            self.topics.addItem(item)
        self.topics.currentItemChanged.connect(self._topic_chosen)
        column.addWidget(self.topics, 1)

        self.count = QLabel("")
        self.count.setObjectName("screenSubheading")
        column.addWidget(self.count)
        return side

    def _build_page(self) -> QWidget:
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QScrollArea.NoFrame)
        self._area = area

        page = QWidget()
        inner = QVBoxLayout(page)
        inner.setContentsMargins(SPACE_ROW, 0, SPACE_ROW, SPACE_ROW)
        inner.setSpacing(SPACE_ROW)

        self.heading = QLabel("")
        self.heading.setObjectName("screenHeading")
        self.heading.setWordWrap(True)
        inner.addWidget(self.heading)

        self.body = QLabel("")
        self.body.setTextFormat(Qt.RichText)
        self.body.setWordWrap(True)
        self.body.setAlignment(Qt.AlignTop)
        self.body.setOpenExternalLinks(True)
        self.body.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse
        )
        inner.addWidget(self.body)
        inner.addStretch(1)

        area.setWidget(page)
        return area

    # -- behaviour ---------------------------------------------------------

    def show_topic(self, topic: Topic) -> None:
        """Show one topic, and select it in the list."""
        self.heading.setText(topic.title)
        self.body.setText(topic.body.strip())
        self._area.verticalScrollBar().setValue(0)

        for row in range(self.topics.count()):
            item = self.topics.item(row)
            if item.data(Qt.UserRole) == topic.key:
                # Selecting re-enters this method through the signal, so set
                # the text first and let the second pass find nothing to do.
                if self.topics.currentItem() is not item:
                    self.topics.setCurrentItem(item)
                break

    def current_topic(self) -> Topic | None:
        item = self.topics.currentItem()
        if item is None:
            return None
        from .help_content import by_key

        return by_key(item.data(Qt.UserRole))

    def _topic_chosen(self, current: QListWidgetItem | None, _previous=None) -> None:
        if current is None:
            return
        from .help_content import by_key

        topic = by_key(current.data(Qt.UserRole))
        if topic is not None and self.heading.text() != topic.title:
            self.show_topic(topic)

    def _filter(self, text: str) -> None:
        """Hide topics that do not match, searching the body as well as the
        title: someone looking for "keyframe" will not guess the heading."""
        needle = text.strip().lower()
        shown = 0
        for row in range(self.topics.count()):
            item = self.topics.item(row)
            topic = TOPICS[row]
            match = not needle or needle in topic.haystack()
            item.setHidden(not match)
            shown += bool(match)

        total = self.topics.count()
        self.count.setText(
            f"{total} topics" if shown == total else f"{shown} of {total} topics"
        )

        # Move off a selection the search has just hidden, so the page is
        # never showing something the list no longer offers.
        current = self.topics.currentItem()
        if shown and (current is None or current.isHidden()):
            for row in range(self.topics.count()):
                if not self.topics.item(row).isHidden():
                    self.topics.setCurrentRow(row)
                    break

    def _show_shortcuts(self) -> None:
        from .shortcuts_dialog import ShortcutsDialog

        ShortcutsDialog(self).exec()
