"""Screen 3 — fetch each session's details and review the Commons wikitext."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..commons import prepare_file, write_sidecar
from ..ffmpeg import OutputFormat
from ..naming import output_path, unique_path
from .state import AppState
from .widgets import StatusLabel
from .workers import ConvertJob, ConvertWorker, start

COLUMNS = ("", "Clip", "File", "Commons name", "Metadata", "Notes")
COL_SELECT, COL_CLIP, COL_FILE, COL_NAME, COL_META, COL_NOTES = range(6)


class MetadataScreen(QWidget):
    """Per-clip Commons descriptions, plus the convert-to-WebM step."""

    files_ready = Signal()

    def __init__(self, state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self._prepared: dict[int, object] = {}
        self._edited: dict[int, str] = {}
        self._worker: ConvertWorker | None = None
        self._updating = False

        self._build()
        self.state.clips_changed.connect(self.refresh)
        self.state.schedule_changed.connect(self.refresh)

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        layout.addWidget(self._commons_group())

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._table_panel())
        splitter.addWidget(self._preview_panel())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 4)
        layout.addWidget(splitter, 1)
        layout.addWidget(self._action_bar())

    def _commons_group(self) -> QGroupBox:
        group = QGroupBox("Commons details applied to every clip")
        form = QFormLayout(group)
        form.setLabelAlignment(Qt.AlignRight)

        self.license_field = QLineEdit(self.state.settings.commons_license)
        self.license_field.setPlaceholderText("{{Cc-by-sa-4.0}}")
        self.license_field.editingFinished.connect(self.refresh)
        form.addRow("Licence", self.license_field)

        self.categories_field = QLineEdit(
            "; ".join(self.state.settings.commons_categories)
        )
        self.categories_field.setPlaceholderText(
            "WikiConference India 2026; Videos of Wikimedia conferences"
        )
        self.categories_field.editingFinished.connect(self.refresh)
        form.addRow("Categories", self.categories_field)

        self.date_field = QLineEdit(self.state.settings.date_override)
        self.date_field.setPlaceholderText(
            "leave empty to use each session's date from the schedule"
        )
        self.date_field.editingFinished.connect(self.refresh)
        form.addRow("Date override", self.date_field)
        return group

    def _table_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.currentCellChanged.connect(self._row_changed)
        self.table.itemChanged.connect(self._item_changed)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        for text, slot in (
            ("Fetch metadata", self._fetch_metadata),
            ("Select all", lambda: self._set_all(True)),
            ("Select none", lambda: self._set_all(False)),
        ):
            button = QPushButton(text)
            button.setAutoDefault(False)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        return panel

    def _preview_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        self.filename_edit = QLineEdit()
        self.filename_edit.setPlaceholderText("the name this file will have on Commons")
        self.filename_edit.editingFinished.connect(self._filename_edited)
        layout.addWidget(self.filename_edit)

        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText(
            "Select a clip to see its Commons file description."
        )
        font = QFont("monospace")
        font.setStyleHint(QFont.TypeWriter)
        self.editor.setFont(font)
        self.editor.textChanged.connect(self._wikitext_edited)
        layout.addWidget(self.editor, 1)

        self.notes = StatusLabel("")
        layout.addWidget(self.notes)

        buttons = QHBoxLayout()
        revert = QPushButton("Revert to generated")
        revert.setAutoDefault(False)
        revert.clicked.connect(self._revert)
        buttons.addWidget(revert)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        return panel

    def _action_bar(self) -> QWidget:
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)

        self.convert_box = QComboBox()
        for fmt in OutputFormat:
            if fmt.commons_compatible:
                self.convert_box.addItem(fmt.label, fmt)
        index = self.convert_box.findData(self.state.settings.convert_format)
        self.convert_box.setCurrentIndex(max(0, index))
        layout.addWidget(self.convert_box)

        self.convert_button = QPushButton("Convert for Commons")
        self.convert_button.setAutoDefault(False)
        self.convert_button.setToolTip(
            "Transcode the cut clips into an uploadable format"
        )
        self.convert_button.clicked.connect(self._convert)
        layout.addWidget(self.convert_button)

        self.sidecar_button = QPushButton("Write descriptions")
        self.sidecar_button.setAutoDefault(False)
        self.sidecar_button.setToolTip(
            "Save each description as a .txt file beside its video"
        )
        self.sidecar_button.clicked.connect(self._write_sidecars)
        layout.addWidget(self.sidecar_button)

        layout.addStretch(1)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setMaximumWidth(220)
        layout.addWidget(self.progress)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setAutoDefault(False)
        self.cancel_button.setVisible(False)
        self.cancel_button.clicked.connect(self._cancel)
        layout.addWidget(self.cancel_button)

        self.summary = StatusLabel("")
        layout.addWidget(self.summary)
        return bar

    # -- data --------------------------------------------------------------

    def _commons_settings(self):
        settings = self.state.settings
        settings.commons_license = self.license_field.text().strip() or "{{Cc-by-sa-4.0}}"
        settings.commons_categories = [
            part.strip() for part in self.categories_field.text().split(";") if part.strip()
        ]
        settings.date_override = self.date_field.text().strip()
        return self.state.commons_settings()

    def refresh(self) -> None:
        commons_settings = self._commons_settings()
        clips = self.state.clips

        self._updating = True
        self.table.setRowCount(len(clips))
        self._prepared.clear()

        for row, clip in enumerate(clips):
            session = self.state.session_for(clip)
            prepared = prepare_file(
                clip, session=session, settings=commons_settings,
                event_info=self.state.event_info, local_path=clip.output_path,
            )
            if row in self._edited:
                prepared.wikitext = self._edited[row]
            self._prepared[row] = prepared

            select = QTableWidgetItem()
            select.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            select.setCheckState(Qt.Checked if clip.selected else Qt.Unchecked)
            self.table.setItem(row, COL_SELECT, select)

            self.table.setItem(row, COL_CLIP, QTableWidgetItem(clip.programme))

            local = Path(clip.output_path).name if clip.output_path else "not cut yet"
            file_item = QTableWidgetItem(local)
            self.table.setItem(row, COL_FILE, file_item)

            self.table.setItem(row, COL_NAME, QTableWidgetItem(prepared.filename))

            if session:
                meta = "from schedule"
            elif clip.eventyay_id.strip():
                meta = "code not found"
            else:
                meta = "CSV only"
            self.table.setItem(row, COL_META, QTableWidgetItem(meta))

            blocking = [w for w in prepared.warnings if "does not exist yet" not in w]
            self.table.setItem(row, COL_NOTES, QTableWidgetItem("; ".join(blocking)))
            self._colour_row(row, prepared, session)

        self._updating = False
        self._row_changed(self.table.currentRow(), 0, -1, 0)
        self._refresh_summary()

    def _colour_row(self, row: int, prepared, session) -> None:
        serious = any(
            "DO NOT RECORD" in w or "MP4 cannot" in w for w in prepared.warnings
        )
        if serious:
            brush = QBrush(QColor(255, 235, 235))
        elif session:
            brush = QBrush(QColor(232, 245, 233))
        else:
            brush = QBrush(QColor(255, 249, 230))
        for column in range(len(COLUMNS)):
            item = self.table.item(row, column)
            if item:
                item.setBackground(brush)

    def _item_changed(self, item: QTableWidgetItem) -> None:
        if self._updating or item.column() != COL_SELECT:
            return
        row = item.row()
        if 0 <= row < len(self.state.clips):
            self.state.clips[row].selected = item.checkState() == Qt.Checked
            self._refresh_summary()

    def _set_all(self, selected: bool) -> None:
        self._updating = True
        for row, clip in enumerate(self.state.clips):
            clip.selected = selected
            item = self.table.item(row, COL_SELECT)
            if item:
                item.setCheckState(Qt.Checked if selected else Qt.Unchecked)
        self._updating = False
        self._refresh_summary()

    def _row_changed(self, row: int, _c: int, _pr: int, _pc: int) -> None:
        prepared = self._prepared.get(row)
        if prepared is None:
            self.editor.blockSignals(True)
            self.editor.setPlainText("")
            self.editor.blockSignals(False)
            self.filename_edit.setText("")
            self.notes.show_message("")
            return

        self.editor.blockSignals(True)
        self.editor.setPlainText(prepared.wikitext)
        self.editor.blockSignals(False)
        self.filename_edit.setText(prepared.filename)

        if prepared.warnings:
            level = "error" if any(
                "DO NOT RECORD" in w or "MP4 cannot" in w for w in prepared.warnings
            ) else "warn"
            self.notes.show_message(" · ".join(prepared.warnings), level)
        else:
            self.notes.show_message("Ready to upload.", "good")

    def _wikitext_edited(self) -> None:
        row = self.table.currentRow()
        prepared = self._prepared.get(row)
        if prepared is None:
            return
        text = self.editor.toPlainText()
        self._edited[row] = text
        prepared.wikitext = text

    def _filename_edited(self) -> None:
        row = self.table.currentRow()
        prepared = self._prepared.get(row)
        if prepared is None:
            return
        prepared.filename = self.filename_edit.text().strip()
        self._updating = True
        item = self.table.item(row, COL_NAME)
        if item:
            item.setText(prepared.filename)
        self._updating = False

    def _revert(self) -> None:
        row = self.table.currentRow()
        self._edited.pop(row, None)
        self.refresh()

    def _fetch_metadata(self) -> None:
        if not self.state.schedule:
            QMessageBox.information(
                self, "No schedule",
                "Fetch the conference schedule on the first screen, then try again.",
            )
            return
        self.refresh()

    # -- conversion --------------------------------------------------------

    def _convert(self) -> None:
        if self._worker is not None:
            return

        target_format = self.convert_box.currentData()
        if not isinstance(target_format, OutputFormat):
            try:
                target_format = OutputFormat(target_format)
            except (ValueError, TypeError):
                target_format = OutputFormat.WEBM_AV1
        self.state.settings.convert_format = target_format
        settings = self.state.settings
        convert_settings = settings.encoding.with_format(target_format)

        jobs: list[ConvertJob] = []
        for index, clip in enumerate(self.state.clips):
            if not clip.selected or not clip.output_path:
                continue
            source = Path(clip.output_path)
            if not source.is_file():
                continue
            if source.suffix.lstrip(".") == target_format.extension:
                continue  # already in the right format

            target = output_path(
                clip, index + 1, settings.output_directory,
                fmt=target_format,
                filename_template=settings.filename_template,
                subfolder_template=settings.subfolder_template,
                separate_by_format=settings.separate_by_format,
                max_length=settings.slug_max_length,
                ascii_only=settings.ascii_filenames,
                event=settings.event_slug,
            )
            if not convert_settings.overwrite:
                target = unique_path(target)

            jobs.append(ConvertJob(
                index=index, source=str(source), output=str(target),
                settings=convert_settings, duration=clip.duration if clip.is_valid else 0.0,
            ))

        if not jobs:
            QMessageBox.information(
                self, "Nothing to convert",
                "No selected clip needs converting. Cut the clips first, or they "
                "are already in the chosen format.",
            )
            return

        self._worker = ConvertWorker(jobs, ffmpeg_path=settings.ffmpeg_path)
        self._worker.signals.progress.connect(self._convert_progress)
        self._worker.signals.row_finished.connect(self._convert_finished)
        self._worker.signals.log.connect(self.state.log)
        self._worker.signals.finished.connect(self._convert_all_finished)
        self._jobs_by_index = {job.index: job for job in jobs}

        self.progress.setRange(0, len(jobs))
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.cancel_button.setVisible(True)
        self.convert_button.setEnabled(False)
        self._completed = 0
        self.summary.show_message(f"Converting {len(jobs)} clips…", "info")
        start(self._worker)

    def _convert_progress(self, index: int, value: float) -> None:
        item = self.table.item(index, COL_NOTES)
        if item:
            self._updating = True
            item.setText(f"converting… {value * 100:.0f}%")
            self._updating = False

    def _convert_finished(self, index: int, succeeded: bool, message: str) -> None:
        self._completed += 1
        self.progress.setValue(self._completed)
        job = getattr(self, "_jobs_by_index", {}).get(index)
        if succeeded and job and 0 <= index < len(self.state.clips):
            # Point the clip at its uploadable file.
            self.state.clips[index].output_path = job.output
        self._updating = True
        item = self.table.item(index, COL_NOTES)
        if item:
            item.setText("converted" if succeeded else (message or "failed"))
        self._updating = False

    def _convert_all_finished(self, succeeded: bool, summary: str) -> None:
        self._worker = None
        self.progress.setVisible(False)
        self.cancel_button.setVisible(False)
        self.convert_button.setEnabled(True)
        self.summary.show_message(summary, "good" if succeeded else "warn")
        self.refresh()
        self.files_ready.emit()

    def _cancel(self) -> None:
        if self._worker:
            self._worker.cancel()
            self.summary.show_message("Cancelling…", "warn")

    # -- sidecars ----------------------------------------------------------

    def _write_sidecars(self) -> None:
        written = failed = 0
        for row, prepared in self._prepared.items():
            clip = self.state.clips[row] if row < len(self.state.clips) else None
            if clip is None or not clip.selected or not prepared.local_path:
                continue
            try:
                write_sidecar(prepared.local_path, prepared.wikitext)
                written += 1
            except OSError as exc:
                failed += 1
                self.state.log(f"Could not write a description for row {row + 1}: {exc}")

        if written and not failed:
            self.summary.show_message(f"Wrote {written} descriptions.", "good")
        elif written:
            self.summary.show_message(
                f"Wrote {written} descriptions, {failed} failed.", "warn"
            )
        else:
            self.summary.show_message(
                "No descriptions written — cut the clips first.", "warn"
            )

    def _refresh_summary(self) -> None:
        clips = self.state.clips
        if not clips:
            self.summary.show_message("No clips loaded.", "muted")
            return
        selected = [c for c in clips if c.selected]
        uploadable = sum(
            1 for c in selected
            if c.output_path and Path(c.output_path).suffix.lstrip(".") != "mp4"
            and Path(c.output_path).is_file()
        )
        self.summary.show_message(
            f"{len(selected)} selected · {uploadable} ready for Commons",
            "good" if uploadable else "muted",
        )

    def prepared_files(self) -> list[tuple[int, object]]:
        """Selected clips paired with their prepared Commons payloads."""
        result = []
        for row, prepared in sorted(self._prepared.items()):
            if row < len(self.state.clips) and self.state.clips[row].selected:
                prepared.local_path = self.state.clips[row].output_path
                result.append((row, prepared))
        return result
