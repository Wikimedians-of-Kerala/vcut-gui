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
    QStackedWidget,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..models import Clip, ClipStatus, TimecodeError, format_timecode, parse_timecode
from ..naming import output_path, unique_path
from . import icons
from .player_bar import PlayerBar
from .progress_dialog import ConfirmJobDialog, JobProgressDialog, JobSummary
from .theme import SPACE_EDGE, SPACE_ROW
from .state import AppState
from .table_support import configure_table
from .widgets import StatusLabel, row_colour
from . import workers
from .workers import CutJob, CutWorker, start

COLUMNS = ("", "Programme", "Start", "End", "Length", "Code", "Checked", "Status")
COL_SELECT, COL_NAME, COL_START, COL_END, COL_LENGTH, COL_CODE, COL_OK, COL_STATUS = range(8)


class VerifyScreen(QWidget):
    """A player beside the clip list, so each cut can be eyeballed before encoding."""

    finished_cutting = Signal()

    #: Emitted from a worker thread when the player must let go of its file,
    #: and again when it may take it back. Queued, so the work happens on the
    #: GUI thread where Qt requires it.
    _release_requested = Signal()
    _restore_requested = Signal()

    def __init__(self, state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self._worker: CutWorker | None = None
        self._dialog: JobProgressDialog | None = None
        self._updating = False
        self._verified: set[int] = set()
        self._preview_end: float | None = None
        self._seek_on_select = True

        self._build()
        self.state.clips_changed.connect(self.reload)
        self.state.source_changed.connect(self._source_changed)

    # -- construction ------------------------------------------------------

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_EDGE, SPACE_ROW, SPACE_EDGE, SPACE_ROW)
        layout.setSpacing(SPACE_ROW)

        self.panes = QSplitter(Qt.Horizontal)
        self.panes.addWidget(self._player_panel())
        self.panes.addWidget(self._table_panel())
        self.panes.setStretchFactor(0, 5)
        self.panes.setStretchFactor(1, 4)
        self.panes.setSizes([640, 520])

        # A vertical splitter too, so the video and list can be traded off
        # against the transport — useful when checking a lot of cut points.
        # The transport spans the whole window rather than sitting under the
        # video: a full-width timeline makes the clip blocks far easier to
        # read against the length of the recording.
        self.rows = QSplitter(Qt.Vertical)
        self.rows.addWidget(self.panes)
        self.rows.addWidget(self._transport_panel())
        self.rows.setStretchFactor(0, 5)
        self.rows.setStretchFactor(1, 0)
        self.rows.setCollapsible(1, False)
        layout.addWidget(self.rows, 1)
        self._actions = self._action_bar()

    def _player_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        self.video = QVideoWidget()
        self.video.setMinimumSize(320, 180)
        # Black behind the frame, so an unfilled pane reads as "no picture
        # yet" rather than as a gap in the window.
        self.video.setStyleSheet("background: #000;")
        self.video.setAspectRatioMode(Qt.KeepAspectRatio)

        # Shown in the player's place while encoding, when the file has been
        # released to free its decoder. A QVideoWidget cannot carry a label,
        # so the two are stacked and swapped.
        self.video_placeholder = QLabel(
            "The player is closed while encoding,\nso the memory goes to the encoder."
        )
        self.video_placeholder.setObjectName("videoPlaceholder")
        self.video_placeholder.setAlignment(Qt.AlignCenter)
        self.video_placeholder.setMinimumSize(320, 180)
        self.video_placeholder.setWordWrap(True)

        self.video_stack = QStackedWidget()
        self.video_stack.addWidget(self.video)
        self.video_stack.addWidget(self.video_placeholder)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video)
        self.player.positionChanged.connect(self._position_changed)
        self.player.durationChanged.connect(self._duration_changed)
        self.player.errorOccurred.connect(self._player_error)

        # Qt Multimedia loads its own FFmpeg into this process -- 7.1.5,
        # against a system ffmpeg that is often a different major version.
        # Holding a long recording open through it while a child ffmpeg
        # encodes has been implicated in crashes that do not occur with the
        # player idle, so let go of the file before any encode starts.
        # Both run from a worker thread, and Qt widgets may only be touched
        # from the GUI thread. A queued signal hops back across.
        workers.before_encoding(self._release_requested.emit)
        workers.after_encoding(self._restore_requested.emit)
        self._release_requested.connect(
            self.release_player, Qt.QueuedConnection
        )
        self._restore_requested.connect(
            self.restore_player, Qt.QueuedConnection
        )

        layout.addWidget(self.video_stack, 1)
        return panel

    def release_player(self) -> None:
        """Stop playback and let go of the file.

        Called before encoding starts. The position is remembered so the
        player can pick up where it was once the job is done.
        """
        try:
            self._resume_position = self.player.position()
            self.player.stop()
            # stop() alone keeps the decoder and its buffers; clearing the
            # source is what actually closes the file. Measured on a
            # nine-hour recording: 241 MB held open, 190 MB after stop(),
            # and the decoder released only once the source is cleared.
            self.player.setSource(QUrl())
            self.video_stack.setCurrentWidget(self.video_placeholder)
        except RuntimeError:  # the widget may already be gone
            pass

    def restore_player(self) -> None:
        """Reopen the source after an encode, back where it was."""
        path = self.state.source_path
        if not path:
            return
        try:
            self.video_stack.setCurrentWidget(self.video)
            self.player.setSource(QUrl.fromLocalFile(path))
            if getattr(self, "_resume_position", 0):
                self.player.setPosition(self._resume_position)
        except RuntimeError:
            pass

    def _transport_panel(self) -> QWidget:
        """The timeline and transport, full width under both panes."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(6)

        self.bar = PlayerBar()
        self.bar.play_toggled.connect(self._toggle_play)
        self.bar.nudged.connect(self._nudge)
        self.bar.go_to_start.connect(self._goto_start)
        self.bar.go_to_end.connect(self._goto_end)
        self.bar.preview_requested.connect(self._preview)
        self.bar.scrubbed.connect(self.player.setPosition)
        self.bar.seek_requested.connect(self._seek_seconds)
        self.bar.clip_clicked.connect(self._select_clip)
        # Marking lives in the bar itself, beside the playhead it reads from.
        self.bar.mark_in.connect(lambda: self._set_from_player(COL_START))
        self.bar.mark_out.connect(lambda: self._set_from_player(COL_END))
        layout.addWidget(self.bar)
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
        # Every column is draggable: ResizeToContents and Stretch sections
        # cannot be resized by hand at all, which is why the dividers looked
        # inert. The title column still takes the slack as the window grows.
        for column in range(len(COLUMNS)):
            header.setSectionResizeMode(column, QHeaderView.Interactive)
        header.setStretchLastSection(False)
        # Narrow enough to fit the default pane without a scrollbar; the
        # user can widen any of them, and the title column takes the slack
        # when the window grows.
        for column, width in (
            (COL_SELECT, 32), (COL_NAME, 210), (COL_START, 76), (COL_END, 76),
            (COL_LENGTH, 76), (COL_CODE, 72), (COL_OK, 62), (COL_STATUS, 150),
        ):
            header.resizeSection(column, width)
        header.setMinimumSectionSize(34)
        header.setSectionsMovable(True)
        header.setCascadingSectionResizes(True)
        configure_table(self.table)
        layout.addWidget(self.table, 1)

        edits = QHBoxLayout()
        for text, tip, role, slot in (
            ("Add clip", "Add a new clip at the current playback position",
             "add", self._add_clip),
            ("Duplicate", "Copy the selected clip", "duplicate", self._duplicate_clip),
            ("Remove", "Delete the selected clip from the list",
             "remove", self._remove_clip),
        ):
            button = QPushButton(text)
            button.setAutoDefault(False)
            button.setToolTip(tip)
            icons.apply(button, role)
            button.setProperty("iconRole", role)
            button.clicked.connect(slot)
            edits.addWidget(button)
        edits.addStretch(1)

        self.save_button = QPushButton("Save list…")
        self.save_button.setAutoDefault(False)
        self.save_button.setToolTip("Write the edited clip list back out as a CSV")
        icons.apply(self.save_button, "save")
        self.save_button.setProperty("iconRole", "save")
        self.save_button.clicked.connect(self._save_list)
        edits.addWidget(self.save_button)
        layout.addLayout(edits)

        marks = QHBoxLayout()
        verified = QPushButton("Mark checked")
        verified.setAutoDefault(False)
        verified.setToolTip("Mark this clip as verified and move to the next")
        icons.apply(verified, "check")
        verified.setProperty("iconRole", "check")
        verified.clicked.connect(self._mark_verified)
        marks.addWidget(verified)

        select_all = QPushButton("Select all")
        select_all.setAutoDefault(False)
        icons.apply(select_all, "select-all")
        select_all.setProperty("iconRole", "select-all")
        select_all.clicked.connect(lambda: self._set_all_selected(True))
        marks.addWidget(select_all)

        select_none = QPushButton("Select none")
        select_none.setAutoDefault(False)
        icons.apply(select_none, "select-none")
        select_none.setProperty("iconRole", "select-none")
        select_none.clicked.connect(lambda: self._set_all_selected(False))
        marks.addWidget(select_none)
        marks.addStretch(1)

        # The transport bar has these too, but the useful moment for them is
        # right after picking a row, so they belong beside the list as well.
        for text, tip, role, slot in (
            ("Go to start", "Jump the player to this clip's start time",
             "go-start", self._goto_start),
            ("Go to end", "Jump the player to this clip's end time",
             "go-end", self._goto_end),
            ("Zoom to clip", "Fill the timeline with just this clip",
             "zoom-in", self._zoom_to_clip),
        ):
            button = QPushButton(text)
            button.setAutoDefault(False)
            button.setToolTip(tip)
            icons.apply(button, role)
            button.setProperty("iconRole", role)
            button.clicked.connect(slot)
            marks.addWidget(button)

        layout.addLayout(marks)

        self.row_status = StatusLabel("")
        layout.addWidget(self.row_status)
        return panel

    def action_widgets(self) -> QWidget:
        """This screen's buttons, for the window's shared bottom row."""
        return self._actions

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
        icons.apply(self.cancel_button, "cancel")
        self.cancel_button.setProperty("iconRole", "cancel")
        self.cancel_button.clicked.connect(self._cancel)
        layout.addWidget(self.cancel_button)

        self.split_button = QPushButton("Split the video")
        self.split_button.setDefault(True)
        icons.apply(self.split_button, "cut")
        self.split_button.setProperty("iconRole", "cut")
        self.split_button.clicked.connect(self.start_cutting)
        layout.addWidget(self.split_button)
        return bar

    def verified_rows(self) -> set[int]:
        """Which clips have been checked, for saving with the project."""
        return set(self._verified)

    def set_verified_rows(self, rows) -> None:
        self._verified = set(rows)
        self.reload()

    def restyle(self) -> None:
        """Repaint what does not follow the palette on its own."""
        self.bar.restyle()
        icons.restyle_widget(self)
        for row, clip in enumerate(self.state.clips):
            self._colour_row(row, clip)

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
        self._refresh_blocks()
        self._refresh_summary()
        if self.state.clips and self.table.currentRow() < 0:
            self.table.setCurrentCell(0, COL_NAME)
        elif not self.state.clips:
            self._highlight_span(None)

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
        if row == self.table.currentRow():
            self._highlight_span(clip)
        self._refresh_blocks()
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
            self._highlight_span(None)
            return
        problems = clip.validate(self.state.source_duration or None)
        if problems:
            self.row_status.show_message("; ".join(problems), "error")
        else:
            self.row_status.show_message("")
        self._highlight_span(clip)
        if self._seek_on_select:
            self._goto_start()

    def _select_clip(self, index: int) -> None:
        """Select the clip whose block was clicked on the timeline."""
        if 0 <= index < self.table.rowCount():
            # Selecting a row normally seeks to its start; the click has
            # already placed the playhead, so leave it where the user put it.
            self._seek_on_select = False
            try:
                self.table.setCurrentCell(index, COL_NAME)
            finally:
                self._seek_on_select = True

    def _refresh_blocks(self) -> None:
        """Redraw the markers for every clip in the list."""
        spans = []
        for clip in self.state.clips:
            try:
                spans.append((clip.start_seconds, clip.end_seconds))
            except TimecodeError:
                continue  # a row still being typed has nothing to mark
        self.bar.set_clip_blocks(spans)

    def _zoom_to_clip(self) -> None:
        """Fill the timeline with the selected clip, for precise trimming."""
        _, clip = self._current_clip()
        if clip is None:
            return
        try:
            self.bar.zoom_to_clip(clip.start_seconds, clip.end_seconds)
        except TimecodeError:
            pass

    def _highlight_span(self, clip: Clip | None) -> None:
        """Show the clip's extent on the scrubber."""
        if clip is None:
            self.bar.set_clip_span(None, None)
            return
        try:
            self.bar.set_clip_span(clip.start_seconds, clip.end_seconds)
        except TimecodeError:
            # A half-typed timecode just means nothing to highlight yet.
            self.bar.set_clip_span(None, None)

    def _toggle_play(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
            self._set_play_button("Play", "play")
        else:
            self.player.play()
            self._set_play_button("Pause", "pause")

    def _set_play_button(self, _text: str, role: str) -> None:
        self.bar.set_playing(role == "pause")

    # -- keyboard actions --------------------------------------------------
    #
    # Named for what the key does rather than how far it moves, so the
    # shortcut table reads as intent and the amounts live in one place.

    def _frame_step(self) -> int:
        """Milliseconds in one frame of the source, defaulting to 25 fps."""
        info = self.state.media_info
        fps = info.fps if info and info.fps else 25.0
        return max(1, round(1000 / fps))

    def _frame_back(self) -> None:
        self._pause_if_playing()
        self._nudge(-self._frame_step())

    def _frame_forward(self) -> None:
        self._pause_if_playing()
        self._nudge(self._frame_step())

    def _shuttle_back(self) -> None:
        self._nudge(-1000)

    def _shuttle_forward(self) -> None:
        self._nudge(1000)

    def _jump_back(self) -> None:
        self._nudge(-10_000)

    def _jump_forward(self) -> None:
        self._nudge(10_000)

    def _pause_if_playing(self) -> None:
        """Stepping a frame while playing is meaningless; stop first."""
        from PySide6.QtMultimedia import QMediaPlayer

        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
            self._set_play_button("Play", "play")

    def _mark_in(self) -> None:
        self._set_from_player(COL_START)

    def _mark_out(self) -> None:
        self._set_from_player(COL_END)

    def _select_all_clips(self) -> None:
        self._set_all_selected(True)

    def _select_no_clips(self) -> None:
        self._set_all_selected(False)

    def _zoom_in(self) -> None:
        self.bar.zoom_in()

    def _zoom_out(self) -> None:
        self.bar.zoom_out()

    def _zoom_reset(self) -> None:
        self.bar.zoom_reset()

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
        self._set_play_button("Pause", "pause")

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
        self._highlight_span(clip)
        self._refresh_blocks()
        self._refresh_summary()

    def _position_changed(self, position_ms: int) -> None:
        self.bar.set_position(position_ms)
        if self._preview_end is not None and position_ms / 1000 >= self._preview_end:
            self.player.pause()
            self._set_play_button("Play", "play")
            self._preview_end = None

    def _duration_changed(self, duration_ms: int) -> None:
        self.bar.set_duration(duration_ms)

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

    def cut_box_label(self) -> str:
        """How the chosen cut mode reads in a summary."""
        from ..ffmpeg import CutMode

        return {
            CutMode.SMART: "Accurate, fast seek",
            CutMode.COPY: "Stream copy (snaps to keyframes)",
            CutMode.REENCODE: "Accurate, decode from the start",
        }.get(self.state.settings.encoding.cut_mode, "")

    def _estimate_seconds(self, jobs: list, total_seconds: float) -> float:
        """A rough guess at how long the batch will take.

        Stream copy is effectively instant; re-encoding runs at a speed that
        depends heavily on the codec, so these are deliberately broad.
        """
        from ..ffmpeg import CutMode, OutputFormat

        settings = self.state.settings.encoding
        if settings.cut_mode is CutMode.COPY and settings.output_format is OutputFormat.MP4:
            return max(2.0, len(jobs) * 0.5)
        rate = {
            OutputFormat.MP4: 0.25,        # x264 is several times realtime
            OutputFormat.WEBM_AV1: 0.6,
            OutputFormat.WEBM_VP9: 1.2,
            OutputFormat.OGV: 0.5,
        }.get(settings.output_format, 0.5)
        return total_seconds * rate

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
        encoding = settings.encoding
        total_seconds = sum(job.end - job.start for job in jobs)

        rows = [
            ("Clips to cut", str(len(jobs))),
            ("Total video", format_timecode(total_seconds)),
            ("Format", encoding.output_format.label.split(" — ")[0]),
            ("Cutting", self.cut_box_label()),
            ("Writing to", settings.output_directory),
        ]
        if skipped:
            rows.append(("Skipped (has problems)", str(skipped)))
        if unchecked:
            rows.append(("Not yet checked", str(unchecked)))

        warning = ""
        if unchecked:
            warning = (
                f"{unchecked} of these clips have not been marked as checked. "
                f"Cutting them now means their start and end times have not "
                f"been seen against the video."
            )
        if settings.dry_run:
            warning = "Dry run: the commands will be shown but nothing encoded."

        summary = JobSummary(
            title="Split the video",
            action="Split the video",
            intro=(
                f"About to cut {len(jobs)} clips out of "
                f"{Path(self.state.source_path).name}."
            ),
            rows=rows,
            warning=warning,
            estimate_seconds=self._estimate_seconds(jobs, total_seconds),
        )
        if ConfirmJobDialog(summary, self).exec() != ConfirmJobDialog.Accepted:
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

        self._dialog = JobProgressDialog(
            "Splitting the video",
            [Path(job.output).name for job in jobs],
            parent=self,
            note=f"Writing to {settings.output_directory}",
        )
        for row, job in enumerate(jobs):
            self._dialog.track(job.index, row)
        self._dialog.cancelled.connect(self._cancel)

        start(self._worker)
        self._dialog.exec()

    def _job_progress(self, index: int, value: float) -> None:
        if not (0 <= index < len(self.state.clips)):
            return
        clip = self.state.clips[index]
        clip.status = ClipStatus.RUNNING
        clip.progress = value
        if self._dialog is not None:
            self._dialog.set_progress(index, value)
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
        if self._dialog is not None:
            self._dialog.set_finished(index, succeeded, message)

        self._updating = True
        item = self.table.item(index, COL_STATUS)
        if item:
            item.setText("done" if succeeded else (message or "failed"))
        self._colour_row(index, clip)
        self._updating = False

    def _all_finished(self, succeeded: bool, summary: str) -> None:
        self._worker = None
        if self._dialog is not None:
            self._dialog.complete(summary)
        self.progress.setVisible(False)
        self.cancel_button.setVisible(False)
        self.split_button.setEnabled(True)
        self.summary.show_message(summary, "good" if succeeded else "warn")
        self.finished_cutting.emit()

    def _cancel(self) -> None:
        if self._worker:
            self._worker.cancel()
            self.summary.show_message("Cancelling…", "warn")
