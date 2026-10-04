"""Small reusable widgets."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)


class FilePicker(QWidget):
    """A read-only path field with a Browse button and drag-and-drop."""

    path_changed = Signal(str)

    def __init__(
        self,
        placeholder: str = "",
        *,
        file_filter: str = "All files (*)",
        directory: bool = False,
        save: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._filter = file_filter
        self._directory = directory
        self._save = save

        self.field = QLineEdit()
        self.field.setPlaceholderText(placeholder)
        self.field.setClearButtonEnabled(True)
        self.field.editingFinished.connect(
            lambda: self.path_changed.emit(self.field.text().strip())
        )

        browse = QPushButton("Browse…")
        browse.setAutoDefault(False)
        from . import icons

        icons.apply(browse, "folder")
        browse.setProperty("iconRole", "folder")
        browse.clicked.connect(self._browse)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.field, 1)
        layout.addWidget(browse)

        self.setAcceptDrops(True)

    def _browse(self) -> None:
        start = self.field.text().strip() or str(Path.home())
        if self._directory:
            chosen = QFileDialog.getExistingDirectory(self, "Choose a folder", start)
        elif self._save:
            chosen, _ = QFileDialog.getSaveFileName(self, "Choose a file", start, self._filter)
        else:
            chosen, _ = QFileDialog.getOpenFileName(self, "Choose a file", start, self._filter)
        if chosen:
            self.set_path(chosen)

    def set_path(self, path: str) -> None:
        if path != self.field.text():
            self.field.setText(path)
        self.path_changed.emit(path)

    def path(self) -> str:
        return self.field.text().strip()

    # -- drag and drop -----------------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        urls = event.mimeData().urls()
        if not urls:
            return
        path = urls[0].toLocalFile()
        if path:
            self.set_path(path)
            event.acceptProposedAction()


class StatusLabel(QLabel):
    """A label that colours itself by severity."""

    LEVELS = {
        "info": "palette(text)",
        "muted": "gray",
        "good": "#1a7f37",
        "warn": "#9a6700",
        "error": "#b42318",
    }

    def __init__(self, text: str = "", level: str = "muted", parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setWordWrap(True)
        self.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.set_level(level)

    def set_level(self, level: str) -> None:
        self.setStyleSheet(f"color: {self.LEVELS.get(level, 'palette(text)')};")

    def show_message(self, text: str, level: str = "info") -> None:
        self.setText(text)
        self.set_level(level)


def space_form(form, *, label_gap: int = 14) -> None:
    """Give a form the shared spacing.

    Qt's default row spacing is tighter than the padding inside the fields
    themselves, which reads as though the text is closer to other rows than
    to its own border. Setting both here keeps every form consistent.
    """
    from .theme import SPACE_ROW

    form.setVerticalSpacing(SPACE_ROW)
    form.setHorizontalSpacing(label_gap)
    form.setContentsMargins(0, 0, 0, 0)


def with_note(widget, *notes, gap: int = 4):
    """Pair a field with the notes and options belonging to it, as one row.

    Anything added as its own ``addRow("", ...)`` picks up the full row gap,
    which pushes it away from the field it describes and leaves it floating
    between two rows. Keeping them in one widget means they sit just under
    their field, and the row spacing falls between the groups instead.
    """
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    holder = QWidget()
    layout = QVBoxLayout(holder)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(gap)
    layout.addWidget(widget)
    for note in notes:
        layout.addWidget(note)
    return holder


def is_dark_theme() -> bool:
    """Whether the palette currently in force is a dark one.

    Reads the application palette rather than the desktop's preference, so it
    reflects an explicitly chosen theme as well as the system default.
    """
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return False
    window = app.palette().window().color()
    # Perceived brightness; below the midpoint reads as a dark theme.
    brightness = (window.red() * 299 + window.green() * 587 + window.blue() * 114) / 1000
    return brightness < 128


def row_colour(kind: str):
    """A row background that stays legible in both light and dark themes.

    Returns ``None`` for "no tint", which leaves the row with the normal
    alternating colours.
    """
    from PySide6.QtGui import QColor

    if kind == "none":
        return None
    dark = is_dark_theme()
    palette = {
        # kind: (light, dark)
        "error": ("#ffe8e8", "#4a2222"),
        "good": ("#e8f5e9", "#1f3a24"),
        "warn": ("#fff6e0", "#43381c"),
        "info": ("#eaf2ff", "#1e2d44"),
    }
    pair = palette.get(kind)
    if not pair:
        return None
    return QColor(pair[1] if dark else pair[0])


def human_size(num_bytes: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num_bytes) < 1024:
            return f"{num_bytes:.0f} {unit}" if unit == "B" else f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} PB"


def human_duration(seconds: float) -> str:
    seconds = int(max(0, seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}h {minutes}m {secs}s"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"
