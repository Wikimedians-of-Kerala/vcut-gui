"""Screen 2 — watch each cut point, correct it, then split the video."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QBrush
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..models import Clip, ClipStatus, TimecodeError, format_timecode, parse_timecode
from ..naming import output_path, unique_path
from .state import AppState
from .widgets import StatusLabel, row_colour
from .workers import CutJob, CutWorker, start

COLUMNS = ("", "Programme", "Start", "End", "Length", "Code", "Checked", "Status")
COL_SELECT, COL_NAME, COL_START, COL_END, COL_LENGTH, COL_CODE, COL_OK, COL_STATUS = range(8)


class VerifyScreen(QWidget):
    """A player beside the clip list, so each cut can be eyeballed before encoding."""

    finished_cutting = Signal()

    def __init__(self, state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self._worker: CutWorker | None = None
        self._updating = False
        self._verified: set[int] = set()
        self._preview_end: float | None = None

        self._build()
        self.state.clips_changed.connect(self.reload)
        self.state.source_changed.connect(self._source_changed)

    # -- construction ------------------------------------------------------

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._player_panel())
        splitter.addWidget(self._table_panel())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 4)
        layout.addWidget(splitter, 1)
        layout.addWidget(self._action_bar())

    def _player_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        self.video = QVideoWidget()
        self.video.setMinimumSize(320, 200)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video)
        self.player.positionChanged.connect(self._position_changed)
        self.player.durationChanged.connect(self._duration_changed)
        self.player.errorOccurred.connect(self._player_error)
        layout.addWidget(self.video, 1)

        self.scrubber = QSlider(Qt.Horizontal)
        self.scrubber.setRange(0, 0)
        self.scrubber.sliderMoved.connect(self.player.setPosition)
        layout.addWidget(self.scrubber)

        controls = QHBoxLayout()
        self.play_button = QPushButton("Play")
        self.play_button.setAutoDefault(False)
        self.play_button.clicked.connect(self._toggle_play)
        controls.addWidget(self.play_button)

        for label, delta in (("-10s", -10_000), ("-1s", -1000),
                             ("+1s", 1000), ("+10s", 10_000)):
            button = QPushButton(label)
            button.setAutoDefault(False)
            button.setFixedWidth(52)
            button.clicked.connect(lambda _=False, d=delta: self._nudge(d))
            controls.addWidget(button)

        self.time_label = QLabel("00:00:00")
        self.time_label.setMinimumWidth(70)
        controls.addWidget(self.time_label)
        controls.addStretch(1)
        layout.addLayout(controls)

        jumps = QHBoxLayout()
        for text, tip, slot in (
            ("Go to start", "Jump to this clip's start time", self._goto_start),
            ("Go to end", "Jump to this clip's end time", self._goto_end),
            ("Preview", "Play the first few seconds of this clip", self._preview),
        ):
            button = QPushButton(text)
            button.setAutoDefault(False)
            button.setToolTip(tip)
            button.clicked.connect(slot)
            jumps.addWidget(button)
        layout.addLayout(jumps)

        grabs = QHBoxLayout()
        set_start = QPushButton("Set start from player")
        set_start.setAutoDefault(False)
        set_start.setToolTip("Use the current playback position as this clip's start")
        set_start.clicked.connect(lambda: self._set_from_player(COL_START))
        set_end = QPushButton("Set end from player")
        set_end.setAutoDefault(False)
        set_end.setToolTip("Use the current playback position as this clip's end")
        set_end.clicked.connect(lambda: self._set_from_player(COL_END))
        grabs.addWidget(set_start)
        grabs.addWidget(set_end)
        layout.addLayout(grabs)
        return panel

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
        self.table.currentCellChanged.connect(self._row_changed)
        self.table.itemChanged.connect(self._item_changed)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(COL_NAME, QHeaderView.Stretch)
        for column in (COL_SELECT, COL_START, COL_END, COL_LENGTH,
                       COL_CODE, COL_OK, COL_STATUS):
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        layout.addWidget(self.table, 1)

        edits = QHBoxLayout()
        for text, tip, slot in (
            ("Add clip", "Add a new clip at the current playback position", self._add_clip),
            ("Duplicate", "Copy the selected clip", self._duplicate_clip),
            ("Remove", "Delete the selected clip from the list", self._remove_clip),
        ):
            button = QPushButton(text)
            button.setAutoDefault(False)
            button.setToolTip(tip)
            button.clicked.connect(slot)
            edits.addWidget(button)
        edits.addStretch(1)

        self.save_button = QPushButton("Save list…")
        self.save_button.setAutoDefault(False)
        self.save_button.setToolTip("Write the edited clip list back out as a CSV")
        self.save_button.clicked.connect(self._save_list)
        edits.addWidget(self.save_button)
        layout.addLayout(edits)

        marks = QHBoxLayout()
        verified = QPushButton("Mark checked")
        verified.setAutoDefault(False)
        verified.setToolTip("Mark this clip as verified and move to the next")
        verified.clicked.connect(self._mark_verified)
        marks.addWidget(verified)

        select_all = QPushButton("Select all")
        select_all.setAutoDefault(False)
        select_all.clicked.connect(lambda: self._set_all_selected(True))
        marks.addWidget(select_all)

        select_none = QPushButton("Select none")
        select_none.setAutoDefault(False)
        select_none.clicked.connect(lambda: self._set_all_selected(False))
        marks.addWidget(select_none)
        marks.addStretch(1)
        layout.addLayout(marks)

        self.row_status = StatusLabel("")
        layout.addWidget(self.row_status)
        return panel

    def _action_bar(self) -> QWidget:
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)

        self.summary = StatusLabel("Load a video and a timecode list to begin.")
        layout.addWidget(self.summary, 1)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setMaximumWidth(220)
        layout.addWidget(self.progress)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setAutoDefault(False)
        self.cancel_button.setVisible(False)
        self.cancel_button.clicked.connect(self._cancel)
        layout.addWidget(self.cancel_button)

        self.split_button = QPushButton("Split the video")
        self.split_button.setDefault(True)
        self.split_button.clicked.connect(self.start_cutting)
        layout.addWidget(self.split_button)
        return bar

    # -- loading -----------------------------------------------------------

    def _source_changed(self, path: str) -> None:
        self.player.stop()
        if path and Path(path).is_file():
            self.player.setSource(QUrl.fromLocalFile(path))
        else:
            self.player.setSource(QUrl())
        self.reload()

    def reload(self) -> None:
        self._updating = True
        self.table.setRowCount(len(self.state.clips))
        for row, clip in enumerate(self.state.clips):
            self._fill_row(row, clip)
        self._updating = False
        self._refresh_summary()
        if self.state.clips and self.table.currentRow() < 0:
            self.table.setCurrentCell(0, COL_NAME)

    def _fill_row(self, row: int, clip: Clip) -> None:
        select = QTableWidgetItem()
        select.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        select.setCheckState(Qt.Checked if clip.selected else Qt.Unchecked)
        self.table.setItem(row, COL_SELECT, select)

        name = QTableWidgetItem(clip.programme)
        self.table.setItem(row, COL_NAME, name)

        self.table.setItem(row, COL_START, QTableWidgetItem(clip.start_time))
        self.table.setItem(row, COL_END, QTableWidgetItem(clip.end_time))

        length = QTableWidgetItem(self._length_text(clip))
        length.setFlags(Qt.ItemIsEnabled)
        self.table.setItem(row, COL_LENGTH, length)

        code = QTableWidgetItem(clip.eventyay_id)
        self.table.setItem(row, COL_CODE, code)

        checked = QTableWidgetItem("yes" if row in self._verified else "")
        checked.setFlags(Qt.ItemIsEnabled)
        checked.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(row, COL_OK, checked)

        status = QTableWidgetItem(self._status_text(clip))
        status.setFlags(Qt.ItemIsEnabled)
        self.table.setItem(row, COL_STATUS, status)

        self._colour_row(row, clip)

    def _length_text(self, clip: Clip) -> str:
        try:
            return format_timecode(clip.duration)
        except (TimecodeError, ValueError):
            return "—"

    def _status_text(self, clip: Clip) -> str:
        if clip.status is ClipStatus.RUNNING:
            return f"{clip.progress * 100:.0f}%"
        if clip.status is ClipStatus.DONE:
            return "done"
        if clip.status is ClipStatus.FAILED:
            return clip.message or "failed"
        problems = clip.validate(self.state.source_duration or None)
        return problems[0] if problems else ""

    def _colour_row(self, row: int, clip: Clip) -> None:
        problems = clip.validate(self.state.source_duration or None)
        if clip.status is ClipStatus.FAILED or problems:
            kind = "error"
        elif clip.status is ClipStatus.DONE:
            kind = "good"
        elif row in self._verified:
            kind = "info"
        else:
            kind = "none"
        colour = row_colour(kind)
        brush = QBrush(colour) if colour else QBrush(Qt.NoBrush)
        for column in range(len(COLUMNS)):
            item = self.table.item(row, column)
            if item:
                item.setBackground(brush)

    # -- editing -----------------------------------------------------------

    def _item_changed(self, item: QTableWidgetItem) -> None:
        if self._updating:
            return
        row, column = item.row(), item.column()
        if row >= len(self.state.clips):
            return
        clip = self.state.clips[row]

        if column == COL_SELECT:
            clip.selected = item.checkState() == Qt.Checked
        elif column == COL_NAME:
            clip.programme = item.text().strip()
        elif column == COL_CODE:
            clip.eventyay_id = item.text().strip()
        elif column in (COL_START, COL_END):
            text = item.text().strip()
            try:
                parse_timecode(text)
            except TimecodeError:
                self.row_status.show_message(
                    f"'{text}' is not a timecode — use HH:MM:SS.", "error"
                )
            else:
                if column == COL_START:
                    clip.start_time = text
                else:
                    clip.end_time = text
                # Editing a time invalidates any earlier check of this clip.
                self._verified.discard(row)
                self.row_status.show_message("")

        self._updating = True
        self.table.item(row, COL_LENGTH).setText(self._length_text(clip))
        self.table.item(row, COL_OK).setText("yes" if row in self._verified else "")
        self.table.item(row, COL_STATUS).setText(self._status_text(clip))
        self._colour_row(row, clip)
        self._updating = False
        self._refresh_summary()

    def _set_all_selected(self, selected: bool) -> None:
        self._updating = True
        for row, clip in enumerate(self.state.clips):
            clip.selected = selected
            item = self.table.item(row, COL_SELECT)
            if item:
                item.setCheckState(Qt.Checked if selected else Qt.Unchecked)
        self._updating = False
        self._refresh_summary()

    # -- player ------------------------------------------------------------

    def _current_clip(self) -> tuple[int, Clip] | tuple[int, None]:
        row = self.table.currentRow()
        if 0 <= row < len(self.state.clips):
            return row, self.state.clips[row]
        return -1, None

    def _row_changed(self, row: int, _column: int, _prev_row: int, _prev: int) -> None:
        _, clip = self._current_clip()
        if clip is None:
            return
        problems = clip.validate(self.state.source_duration or None)
        if problems:
            self.row_status.show_message("; ".join(problems), "error")
        else:
            self.row_status.show_message("")
        self._goto_start()

    def _toggle_play(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
            self.play_button.setText("Play")
        else:
            self.player.play()
            self.play_button.setText("Pause")

    def _nudge(self, delta_ms: int) -> None:
        self.player.setPosition(max(0, self.player.position() + delta_ms))

    def _seek_seconds(self, seconds: float) -> None:
        self.player.setPosition(int(max(0.0, seconds) * 1000))

    def _goto_start(self) -> None:
        _, clip = self._current_clip()
        if clip is None:
            return
        try:
            self._preview_end = None
            self._seek_seconds(clip.start_seconds)
        except TimecodeError:
            pass

    def _goto_end(self) -> None:
        _, clip = self._current_clip()
        if clip is None:
            return
        try:
            self._preview_end = None
            self._seek_seconds(clip.end_seconds)
        except TimecodeError:
            pass

    def _preview(self, seconds: float = 8.0) -> None:
        _, clip = self._current_clip()
        if clip is None:
            return
        try:
            start = clip.start_seconds
        except TimecodeError:
            return
        self._seek_seconds(start)
        self._preview_end = start + seconds
        self.player.play()
        self.play_button.setText("Pause")

    def _set_from_player(self, column: int) -> None:
        row, clip = self._current_clip()
        if clip is None:
            return
        text = format_timecode(self.player.position() / 1000)
        self._updating = True
        self.table.item(row, column).setText(text)
        self._updating = False
        if column == COL_START:
            clip.start_time = text
        else:
            clip.end_time = text
        self._verified.discard(row)
        self._updating = True
        self.table.item(row, COL_LENGTH).setText(self._length_text(clip))
        self.table.item(row, COL_OK).setText("")
        self.table.item(row, COL_STATUS).setText(self._status_text(clip))
        self._colour_row(row, clip)
        self._updating = False
        self._refresh_summary()

    def _position_changed(self, position_ms: int) -> None:
        if not self.scrubber.isSliderDown():
            self.scrubber.setValue(position_ms)
        self.time_label.setText(format_timecode(position_ms / 1000))
        if self._preview_end is not None and position_ms / 1000 >= self._preview_end:
            self.player.pause()
            self.play_button.setText("Play")
            self._preview_end = None

    def _duration_changed(self, duration_ms: int) -> None:
        self.scrubber.setRange(0, duration_ms)

    def _player_error(self, _error, message: str) -> None:
        if message:
            self.row_status.show_message(f"Playback problem: {message}", "warn")

    def _mark_verified(self) -> None:
        row, clip = self._current_clip()
        if clip is None:
            return
        if clip.validate(self.state.source_duration or None):
            self.row_status.show_message("Fix the problems above before marking.", "error")
            return
        self._verified.add(row)
        self._updating = True
        self.table.item(row, COL_OK).setText("yes")
        self._colour_row(row, clip)
        self._updating = False
        self._refresh_summary()
        if row + 1 < self.table.rowCount():
            self.table.setCurrentCell(row + 1, COL_NAME)

    # -- adding and removing rows -----------------------------------------

    def _reindex_verified(self, inserted_at: int | None = None,
                          removed_at: int | None = None) -> None:
        """Keep the 'checked' marks attached to their rows after a change."""
        updated = set()
        for row in self._verified:
            if inserted_at is not None and row >= inserted_at:
                updated.add(row + 1)
            elif removed_at is not None:
                if row == removed_at:
                    continue
                updated.add(row - 1 if row > removed_at else row)
            else:
                updated.add(row)
        self._verified = updated

    def _add_clip(self) -> None:
        """Insert a clip starting at the current playback position.

        Sessions missing from the CSV are common — an unscheduled lightning
        talk, a performance — so a new row starts from where the user is
        already looking in the video.
        """
        position = self.player.position() / 1000
        duration = self.state.source_duration or (self.player.duration() / 1000)
        start = max(0.0, position)
        # A ten-minute default is a sensible session length to trim down from,
        # but never run past the end of the recording.
        end = start + 600
        if duration:
            end = min(end, duration)
        if end <= start:
            end = min(start + 60, duration) if duration else start + 60

        clip = Clip(
            programme="New clip",
            start_time=format_timecode(start),
            end_time=format_timecode(end),
        )
        row = self.table.currentRow()
        insert_at = row + 1 if row >= 0 else len(self.state.clips)
        self.state.clips.insert(insert_at, clip)
        self._reindex_verified(inserted_at=insert_at)

        self.reload()
        self.table.setCurrentCell(insert_at, COL_NAME)
        self.table.editItem(self.table.item(insert_at, COL_NAME))
        self.row_status.show_message(
            "Added a clip starting at the player position — set its end time "
            "and give it a title.",
            "info",
        )

    def _duplicate_clip(self) -> None:
        row, clip = self._current_clip()
        if clip is None:
            return
        import copy

        duplicate = copy.deepcopy(clip)
        duplicate.status = ClipStatus.PENDING
        duplicate.progress = 0.0
        duplicate.message = ""
        duplicate.output_path = ""
        duplicate.programme = f"{clip.programme} (copy)"

        self.state.clips.insert(row + 1, duplicate)
        self._reindex_verified(inserted_at=row + 1)
        self.reload()
        self.table.setCurrentCell(row + 1, COL_NAME)

    def _remove_clip(self) -> None:
        row, clip = self._current_clip()
        if clip is None:
            return
        answer = QMessageBox.question(
            self, "Remove this clip",
            f"Remove {clip.programme or 'this clip'} from the list?\n\n"
            f"Any file already written for it is left alone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        del self.state.clips[row]
        self._reindex_verified(removed_at=row)
        self.reload()
        if self.table.rowCount():
            self.table.setCurrentCell(min(row, self.table.rowCount() - 1), COL_NAME)

    def _save_list(self) -> None:
        """Write the edited list back out, so the changes outlive the session."""
        from PySide6.QtWidgets import QFileDialog

        from ..csvio import write_clips

        suggested = self.state.csv_path or "clips.csv"
        target, _ = QFileDialog.getSaveFileName(
            self, "Save the clip list", suggested, "CSV files (*.csv);;All files (*)"
        )
        if not target:
            return
        try:
            write_clips(target, self.state.clips)
        except OSError as exc:
            QMessageBox.critical(self, "Could not save", str(exc))
            return
        self.row_status.show_message(f"Saved {target}.", "good")

    # -- cutting -----------------------------------------------------------

    def _refresh_summary(self) -> None:
        clips = self.state.clips
        if not clips:
            self.summary.show_message("Load a video and a timecode list to begin.", "muted")
            self.split_button.setEnabled(False)
            return

        selected = [c for c in clips if c.selected]
        problems = sum(
            1 for c in selected if c.validate(self.state.source_duration or None)
        )
        checked = len(self._verified & {i for i, c in enumerate(clips) if c.selected})
        total = sum(c.duration for c in selected if c.is_valid)

        message = (
            f"{len(selected)} of {len(clips)} selected · {checked} checked · "
            f"{format_timecode(total)} of video"
        )
        if problems:
            self.summary.show_message(f"{message} · {problems} with problems", "warn")
        else:
            self.summary.show_message(message, "good")
        self.split_button.setEnabled(bool(selected) and self._worker is None)

    def start_cutting(self) -> None:
        if self._worker is not None:
            return
        if not self.state.source_path:
            QMessageBox.warning(self, "No video", "Choose a source video first.")
            return

        settings = self.state.settings
        if not settings.output_directory:
            QMessageBox.warning(
                self, "No output folder", "Choose where the clips should be written."
            )
            return

        jobs: list[CutJob] = []
        skipped = 0
        for index, clip in enumerate(self.state.clips):
            if not clip.selected:
                continue
            if clip.validate(self.state.source_duration or None):
                skipped += 1
                continue

            target = output_path(
                clip, index + 1, settings.output_directory,
                fmt=settings.encoding.output_format,
                filename_template=settings.filename_template,
                subfolder_template=settings.subfolder_template,
                separate_by_format=settings.separate_by_format,
                max_length=settings.slug_max_length,
                ascii_only=settings.ascii_filenames,
                event=settings.event_slug,
            )
            if not settings.encoding.overwrite:
                target = unique_path(target)
            clip.output_path = str(target)
            clip.status = ClipStatus.PENDING
            clip.progress = 0.0
            clip.message = ""

            jobs.append(CutJob(
                index=index, source=self.state.source_path, output=str(target),
                start=clip.start_seconds, end=clip.end_seconds,
                settings=settings.encoding,
            ))

        if not jobs:
            QMessageBox.information(
                self, "Nothing to cut",
                "No selected clip is ready. Fix the highlighted rows first.",
            )
            return

        unchecked = len(jobs) - len(self._verified & {j.index for j in jobs})
        if unchecked:
            answer = QMessageBox.question(
                self, "Not everything is checked",
                f"{unchecked} of the {len(jobs)} clips have not been marked as "
                f"checked.\n\nCut them anyway?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return

        if skipped:
            self.state.log(f"Skipped {skipped} clips with validation problems.")

        self._worker = CutWorker(
            jobs, ffmpeg_path=settings.ffmpeg_path, dry_run=settings.dry_run
        )
        self._worker.signals.progress.connect(self._job_progress)
        self._worker.signals.row_finished.connect(self._job_finished)
        self._worker.signals.log.connect(self.state.log)
        self._worker.signals.finished.connect(self._all_finished)

        self._total_jobs = len(jobs)
        self._completed_jobs = 0
        self.progress.setRange(0, self._total_jobs)
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.cancel_button.setVisible(True)
        self.split_button.setEnabled(False)
        self.summary.show_message(f"Cutting {len(jobs)} clips…", "info")
        start(self._worker)

    def _job_progress(self, index: int, value: float) -> None:
        if not (0 <= index < len(self.state.clips)):
            return
        clip = self.state.clips[index]
        clip.status = ClipStatus.RUNNING
        clip.progress = value
        item = self.table.item(index, COL_STATUS)
        if item:
            self._updating = True
            item.setText(f"{value * 100:.0f}%")
            self._updating = False

    def _job_finished(self, index: int, succeeded: bool, message: str) -> None:
        if not (0 <= index < len(self.state.clips)):
            return
        clip = self.state.clips[index]
        clip.status = ClipStatus.DONE if succeeded else ClipStatus.FAILED
        clip.message = message
        clip.progress = 1.0 if succeeded else clip.progress

        self._completed_jobs += 1
        self.progress.setValue(self._completed_jobs)

        self._updating = True
        item = self.table.item(index, COL_STATUS)
        if item:
            item.setText("done" if succeeded else (message or "failed"))
        self._colour_row(index, clip)
        self._updating = False

    def _all_finished(self, succeeded: bool, summary: str) -> None:
        self._worker = None
        self.progress.setVisible(False)
        self.cancel_button.setVisible(False)
        self.split_button.setEnabled(True)
        self.summary.show_message(summary, "good" if succeeded else "warn")
        self.finished_cutting.emit()

    def _cancel(self) -> None:
        if self._worker:
            self._worker.cancel()
            self.summary.show_message("Cancelling…", "warn")
