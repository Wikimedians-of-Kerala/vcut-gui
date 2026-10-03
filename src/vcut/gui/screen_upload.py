"""Screen 4 — upload the finished files to Wikimedia Commons."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..manifest import build_entry, write_manifest
from ..upload import check_login, commons_url, validate_for_upload
from .state import AppState
from .widgets import StatusLabel, human_size
from .workers import UploadWorker, start

COLUMNS = ("", "File", "Commons name", "Size", "Status")
COL_SELECT, COL_FILE, COL_NAME, COL_SIZE, COL_STATUS = range(5)


class UploadScreen(QWidget):
    """Check login, review what will be uploaded, then upload."""

    def __init__(self, state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self._worker: UploadWorker | None = None
        self._files: list[tuple[int, object]] = []
        self._updating = False
        self._skip: set[int] = set()
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        login_row = QHBoxLayout()
        self.login_status = StatusLabel("Checking Pywikibot…")
        login_row.addWidget(self.login_status, 1)
        check = QPushButton("Check login")
        check.setAutoDefault(False)
        check.clicked.connect(self.check_login)
        login_row.addWidget(check)
        layout.addLayout(login_row)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.itemChanged.connect(self._item_changed)
        self.table.cellDoubleClicked.connect(self._open_on_commons)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)

        self.comment_field = QLineEdit(
            "Uploading conference session recording with vcut-gui"
        )
        self.comment_field.setPlaceholderText("Upload summary")
        layout.addWidget(self.comment_field)

        options = QHBoxLayout()
        self.dry_run_box = QCheckBox("Dry run — check everything without uploading")
        self.dry_run_box.setChecked(True)
        options.addWidget(self.dry_run_box)
        self.ignore_box = QCheckBox("Ignore Commons warnings (e.g. duplicate names)")
        options.addWidget(self.ignore_box)
        options.addStretch(1)
        layout.addLayout(options)

        actions = QHBoxLayout()
        self.summary = StatusLabel("")
        actions.addWidget(self.summary, 1)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setMaximumWidth(220)
        actions.addWidget(self.progress)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setAutoDefault(False)
        self.cancel_button.setVisible(False)
        self.cancel_button.clicked.connect(self._cancel)
        actions.addWidget(self.cancel_button)

        self.manifest_button = QPushButton("Save metadata to folder")
        self.manifest_button.setAutoDefault(False)
        self.manifest_button.setToolTip(
            "Write the manifest and descriptions so this folder can be uploaded later"
        )
        self.manifest_button.clicked.connect(self.write_manifest_files)
        actions.addWidget(self.manifest_button)

        self.upload_button = QPushButton("Upload to Commons")
        self.upload_button.setDefault(True)
        self.upload_button.clicked.connect(self._upload)
        actions.addWidget(self.upload_button)
        layout.addLayout(actions)

    # -- login -------------------------------------------------------------

    def check_login(self) -> None:
        status = check_login()
        if status.logged_in:
            self.login_status.show_message(status.message, "good")
        elif status.available:
            self.login_status.show_message(status.message, "warn")
        else:
            self.login_status.show_message(status.message, "error")
        return status

    # -- population --------------------------------------------------------

    def set_files(self, files: list[tuple[int, object]]) -> None:
        """Take the prepared Commons payloads from the metadata screen."""
        self._files = files
        self._updating = True
        self.table.setRowCount(len(files))

        for row, (_index, prepared) in enumerate(files):
            problems = validate_for_upload(prepared)

            select = QTableWidgetItem()
            select.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            blocked = bool(problems)
            select.setCheckState(Qt.Unchecked if blocked else Qt.Checked)
            if blocked:
                self._skip.add(row)
            self.table.setItem(row, COL_SELECT, select)

            path = Path(prepared.local_path) if prepared.local_path else None
            self.table.setItem(
                row, COL_FILE, QTableWidgetItem(path.name if path else "—")
            )
            self.table.setItem(row, COL_NAME, QTableWidgetItem(prepared.filename))

            size = ""
            if path and path.is_file():
                size = human_size(path.stat().st_size)
            size_item = QTableWidgetItem(size)
            size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, COL_SIZE, size_item)

            status = QTableWidgetItem("; ".join(problems) if problems else "ready")
            self.table.setItem(row, COL_STATUS, status)
            self._colour_row(row, bool(problems))

        self._updating = False
        self._refresh_summary()

    def _colour_row(self, row: int, blocked: bool, uploaded: bool = False) -> None:
        if uploaded:
            brush = QBrush(QColor(232, 245, 233))
        elif blocked:
            brush = QBrush(QColor(255, 235, 235))
        else:
            brush = QBrush(Qt.NoBrush)
        for column in range(len(COLUMNS)):
            item = self.table.item(row, column)
            if item:
                item.setBackground(brush)

    def _item_changed(self, item: QTableWidgetItem) -> None:
        if self._updating or item.column() != COL_SELECT:
            return
        row = item.row()
        if item.checkState() == Qt.Checked:
            self._skip.discard(row)
        else:
            self._skip.add(row)
        self._refresh_summary()

    def _refresh_summary(self) -> None:
        total = len(self._files)
        ready = total - len(self._skip)
        if not total:
            self.summary.show_message(
                "Nothing prepared yet — cut and convert the clips first.", "muted"
            )
            self.upload_button.setEnabled(False)
            return
        self.summary.show_message(f"{ready} of {total} selected for upload.",
                                  "good" if ready else "warn")
        self.upload_button.setEnabled(bool(ready))

    def _open_on_commons(self, row: int, _column: int) -> None:
        if row >= len(self._files):
            return
        _, prepared = self._files[row]
        if prepared.filename:
            QDesktopServices.openUrl(QUrl(commons_url(prepared.filename)))

    # -- manifest ----------------------------------------------------------

    def write_manifest_files(self) -> None:
        """Write the manifest and per-file descriptions into the output folder."""
        from ..commons import write_sidecar

        if not self._files:
            QMessageBox.information(
                self, "Nothing to save",
                "Prepare the clips on the metadata screen first.",
            )
            return

        directory = self.state.settings.output_directory
        if not directory:
            QMessageBox.warning(self, "No folder", "No output folder is set.")
            return

        entries = []
        sidecars = 0
        for index, prepared in self._files:
            clip = self.state.clips[index] if index < len(self.state.clips) else None
            if clip is None:
                continue
            session = self.state.session_for(clip)
            entries.append(
                build_entry(clip, prepared, session=session, base_directory=directory)
            )
            if prepared.local_path and Path(prepared.local_path).is_file():
                try:
                    write_sidecar(prepared.local_path, prepared.wikitext)
                    sidecars += 1
                except OSError as exc:
                    self.state.log(f"Could not write a description: {exc}")

        try:
            written = write_manifest(
                directory, entries,
                event_info=self.state.event_info,
                source_video=self.state.source_path,
            )
        except OSError as exc:
            QMessageBox.critical(self, "Could not save", str(exc))
            return

        self.summary.show_message(
            f"Saved {written['json'].name}, {written['csv'].name} and "
            f"{sidecars} descriptions to {directory}.",
            "good",
        )

    # -- uploading ---------------------------------------------------------

    def _upload(self) -> None:
        if self._worker is not None:
            return

        dry_run = self.dry_run_box.isChecked()
        if not dry_run:
            status = self.check_login()
            if not status.logged_in:
                QMessageBox.warning(
                    self, "Not logged in",
                    status.message + "\n\nUntick 'Dry run' only once you are logged in.",
                )
                return

            answer = QMessageBox.question(
                self, "Upload to Wikimedia Commons",
                f"This will publicly upload "
                f"{len(self._files) - len(self._skip)} files to Wikimedia Commons "
                f"as {status.username}.\n\nUploads are public and visible "
                f"immediately. Continue?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return

        batch = [
            (row, prepared)
            for row, (_index, prepared) in enumerate(self._files)
            if row not in self._skip
        ]
        if not batch:
            return

        self._worker = UploadWorker(
            batch,
            comment=self.comment_field.text().strip(),
            ignore_warnings=self.ignore_box.isChecked(),
            dry_run=dry_run,
        )
        self._worker.signals.row_finished.connect(self._row_finished)
        self._worker.signals.log.connect(self.state.log)
        self._worker.signals.finished.connect(self._all_finished)

        self.progress.setRange(0, len(batch))
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.cancel_button.setVisible(True)
        self.upload_button.setEnabled(False)
        self._completed = 0
        self.summary.show_message(
            f"{'Checking' if dry_run else 'Uploading'} {len(batch)} files…", "info"
        )
        start(self._worker)

    def _row_finished(self, row: int, succeeded: bool, message: str) -> None:
        self._completed += 1
        self.progress.setValue(self._completed)
        self._updating = True
        item = self.table.item(row, COL_STATUS)
        if item:
            item.setText(message or ("uploaded" if succeeded else "failed"))
        self._colour_row(row, not succeeded, uploaded=succeeded)
        self._updating = False

    def _all_finished(self, succeeded: bool, summary: str) -> None:
        self._worker = None
        self.progress.setVisible(False)
        self.cancel_button.setVisible(False)
        self.upload_button.setEnabled(True)
        self.summary.show_message(summary, "good" if succeeded else "warn")

    def _cancel(self) -> None:
        if self._worker:
            self._worker.cancel()
            self.summary.show_message("Cancelling…", "warn")
