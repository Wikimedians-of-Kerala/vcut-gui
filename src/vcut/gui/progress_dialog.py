"""Confirmation and progress windows for long jobs.

Cutting a day of sessions takes minutes; converting them to AV1 can take
hours. A job that long needs more than a bar in the corner — it needs to say
what it is doing, how far through it is, and what it expects to take, and it
needs to be cancellable without guessing what will be left behind.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import icons
from .widgets import StatusLabel, human_duration


@dataclass
class JobSummary:
    """What a confirmation dialog tells the user before they commit."""

    title: str
    action: str                 # the verb on the go-ahead button
    intro: str
    rows: list[tuple[str, str]]  # label/value pairs
    warning: str = ""
    estimate_seconds: float = 0.0


class ConfirmJobDialog(QDialog):
    """Asks before starting a job, showing what it will do."""

    def __init__(self, summary: JobSummary, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(summary.title)
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 14)
        layout.setSpacing(12)

        intro = QLabel(summary.intro)
        intro.setWordWrap(True)
        layout.addWidget(intro)

        panel = QFrame()
        panel.setObjectName("screenHeadingPanel")
        panel.setAttribute(Qt.WA_StyledBackground, True)
        details = QVBoxLayout(panel)
        details.setContentsMargins(14, 10, 14, 10)
        details.setSpacing(5)
        for label, value in summary.rows:
            row = QHBoxLayout()
            name = QLabel(label)
            name.setObjectName("screenSubheading")
            row.addWidget(name)
            row.addStretch(1)
            reading = QLabel(str(value))
            reading.setTextInteractionFlags(Qt.TextSelectableByMouse)
            row.addWidget(reading)
            details.addLayout(row)
        layout.addWidget(panel)

        if summary.estimate_seconds:
            estimate = StatusLabel(
                f"This is expected to take roughly "
                f"{human_duration(summary.estimate_seconds)}.",
                "muted",
            )
            layout.addWidget(estimate)

        if summary.warning:
            layout.addWidget(StatusLabel(summary.warning, "warn"))

        buttons = QDialogButtonBox()
        self.go = QPushButton(summary.action)
        self.go.setDefault(True)
        buttons.addButton(self.go, QDialogButtonBox.AcceptRole)
        cancel = buttons.addButton(QDialogButtonBox.Cancel)
        cancel.setAutoDefault(False)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class JobProgressDialog(QDialog):
    """Shows a running job: overall progress, the current item, and a log."""

    cancelled = Signal()

    def __init__(self, title: str, jobs: list[str], *,
                 parent: QWidget | None = None, note: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(620, 460)
        # Closing mid-job would orphan the worker; the Cancel button is the way out.
        self.setWindowFlag(Qt.WindowCloseButtonHint, False)

        self._total = len(jobs)
        self._done = 0
        self._failed = 0
        self._started = time.monotonic()
        self._finished = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)

        self.heading = QLabel(title)
        self.heading.setObjectName("screenHeading")
        layout.addWidget(self.heading)

        if note:
            layout.addWidget(StatusLabel(note, "muted"))

        self.overall = QProgressBar()
        self.overall.setRange(0, self._total)
        self.overall.setValue(0)
        self.overall.setFormat(f"%v of {self._total} finished")
        layout.addWidget(self.overall)

        self.current_label = StatusLabel("Starting…", "info")
        layout.addWidget(self.current_label)

        self.current = QProgressBar()
        self.current.setRange(0, 100)
        self.current.setValue(0)
        layout.addWidget(self.current)

        self.table = QTableWidget(len(jobs), 2)
        self.table.setHorizontalHeaderLabels(("File", "Status"))
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 340)
        for row, name in enumerate(jobs):
            self.table.setItem(row, 0, QTableWidgetItem(name))
            self.table.setItem(row, 1, QTableWidgetItem("waiting"))
        layout.addWidget(self.table, 1)

        self.elapsed_label = StatusLabel("", "muted")
        layout.addWidget(self.elapsed_label)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setAutoDefault(False)
        icons.apply(self.cancel_button, "cancel")
        self.cancel_button.clicked.connect(self._cancel)
        buttons.addWidget(self.cancel_button)

        self.close_button = QPushButton("Close")
        self.close_button.setEnabled(False)
        self.close_button.setDefault(True)
        self.close_button.clicked.connect(self.accept)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)

        self._row_for: dict[int, int] = {}

    def track(self, job_index: int, row: int) -> None:
        """Map a worker's clip index onto a row in this dialog."""
        self._row_for[job_index] = row

    # -- updates -----------------------------------------------------------

    def set_progress(self, job_index: int, fraction: float) -> None:
        row = self._row_for.get(job_index)
        if row is None:
            return
        self.current.setValue(int(fraction * 100))
        name = self.table.item(row, 0)
        if name:
            self.current_label.show_message(f"Working on {name.text()}", "info")
        status = self.table.item(row, 1)
        if status:
            status.setText(f"{fraction * 100:.0f}%")
        self._update_elapsed()

    def set_finished(self, job_index: int, succeeded: bool, message: str) -> None:
        row = self._row_for.get(job_index)
        self._done += 1
        if not succeeded:
            self._failed += 1
        self.overall.setValue(self._done)
        if row is not None:
            status = self.table.item(row, 1)
            if status:
                status.setText("done" if succeeded else (message or "failed"))
            self.table.scrollToItem(self.table.item(row, 0))
        self.current.setValue(0)
        self._update_elapsed()

    def _update_elapsed(self) -> None:
        elapsed = time.monotonic() - self._started
        text = f"Running for {human_duration(elapsed)}"
        if self._done and self._done < self._total:
            # A simple average is honest enough, and it settles quickly.
            remaining = (elapsed / self._done) * (self._total - self._done)
            text += f" · about {human_duration(remaining)} left"
        self.elapsed_label.show_message(text, "muted")

    def complete(self, summary: str) -> None:
        self._finished = True
        self.current.setValue(100)
        self.current.setRange(0, 100)
        level = "warn" if self._failed else "good"
        self.current_label.show_message(summary, level)
        self.elapsed_label.show_message(
            f"Finished in {human_duration(time.monotonic() - self._started)}.", "muted"
        )
        self.cancel_button.setEnabled(False)
        self.close_button.setEnabled(True)
        self.close_button.setFocus()

    def _cancel(self) -> None:
        self.cancel_button.setEnabled(False)
        self.current_label.show_message(
            "Cancelling — the clip being written now will be finished first.", "warn"
        )
        self.cancelled.emit()

    def reject(self) -> None:  # noqa: D102 - Esc should not close a running job
        if self._finished:
            super().reject()
