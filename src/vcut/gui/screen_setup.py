"""Screen 1 — choose the source video, the CSV, the event, and the encoding."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..csvio import read_clips
from ..ffmpeg import CutMode, OutputFormat, resolve_av1_encoder


def _as_format(value) -> OutputFormat | None:
    """Qt hands back a plain str for a str-based enum; restore the member."""
    if isinstance(value, OutputFormat):
        return value
    try:
        return OutputFormat(value)
    except (ValueError, TypeError):
        return None


def _as_cut_mode(value) -> CutMode | None:
    if isinstance(value, CutMode):
        return value
    try:
        return CutMode(value)
    except (ValueError, TypeError):
        return None
from ..naming import COMMONS_SUBFOLDER, MP4_SUBFOLDER
from . import icons
from .state import AppState
from .widgets import FilePicker, StatusLabel, human_duration, human_size
from .workers import ProbeWorker, ScheduleWorker, start

VIDEO_FILTER = (
    "Video files (*.mp4 *.mkv *.mov *.webm *.avi *.m4v *.mpg *.mpeg *.ts);;All files (*)"
)
CSV_FILTER = "Timecode lists (*.csv *.tsv *.txt);;All files (*)"


class SetupScreen(QWidget):
    """Everything needed before any video is touched."""

    ready_changed = Signal(bool)

    def __init__(self, state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        # Whether the output folder is still the one we suggested.
        self._output_is_automatic = True
        self._automatic_output = ""
        self._build()
        self._load_from_settings()

    # -- construction ------------------------------------------------------

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        # A group box's title sits above its frame, so without a top margin
        # the first one is clipped by the heading when the page is scrolled.
        scroll.setViewportMargins(0, 6, 0, 0)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(20)

        layout.addWidget(self._files_group())
        layout.addWidget(self._event_group())
        layout.addWidget(self._output_group())
        layout.addWidget(self._encoding_group())
        layout.addStretch(1)

        scroll.setWidget(inner)
        outer.addWidget(scroll)

    def _files_group(self) -> QGroupBox:
        group = QGroupBox("Source files")
        form = QFormLayout(group)
        form.setLabelAlignment(Qt.AlignRight)

        self.source_picker = FilePicker(
            "Drop the full-day recording here, or browse…", file_filter=VIDEO_FILTER
        )
        self.source_picker.path_changed.connect(self._source_chosen)
        self.source_status = StatusLabel("No video chosen yet.")
        form.addRow("Source video", self.source_picker)
        form.addRow("", self.source_status)

        self.csv_picker = FilePicker(
            "Drop the timecode CSV here, or browse…", file_filter=CSV_FILTER
        )
        self.csv_picker.path_changed.connect(self._csv_chosen)
        self.csv_status = StatusLabel("No timecode list loaded yet.")
        form.addRow("Timecode CSV", self.csv_picker)
        form.addRow("", self.csv_status)
        return group

    def _event_group(self) -> QGroupBox:
        group = QGroupBox("Conference schedule")
        form = QFormLayout(group)
        form.setLabelAlignment(Qt.AlignRight)

        self.event_field = QLineEdit()
        self.event_field.setPlaceholderText(
            "india26, wikicon/india26, or a full schedule URL"
        )
        self.event_field.editingFinished.connect(self._remember_event)

        fetch = QPushButton("Fetch schedule")
        fetch.setAutoDefault(False)
        icons.apply(fetch, "schedule")
        fetch.setProperty("iconRole", "schedule")
        fetch.clicked.connect(lambda: self.fetch_schedule(force=True))
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.event_field, 1)
        row.addWidget(fetch)
        holder = QWidget()
        holder.setLayout(row)
        form.addRow("Event", holder)

        self.offline_box = QCheckBox("Work offline (use the cached schedule only)")
        form.addRow("", self.offline_box)

        self.event_status = StatusLabel("Metadata is optional — cutting works without it.")
        form.addRow("", self.event_status)
        return group

    def _output_group(self) -> QGroupBox:
        group = QGroupBox("Output")
        form = QFormLayout(group)
        form.setLabelAlignment(Qt.AlignRight)

        self.output_picker = FilePicker("Where the clips should be written", directory=True)
        self.output_picker.path_changed.connect(self._remember_output)
        form.addRow("Folder", self.output_picker)

        self.output_status = StatusLabel("")
        form.addRow("", self.output_status)

        self.filename_field = QLineEdit()
        self.filename_field.setPlaceholderText("{index:02d}-{programme}")
        form.addRow("File names", self.filename_field)

        self.subfolder_field = QLineEdit()
        self.subfolder_field.setPlaceholderText("optional, e.g. {room}")
        form.addRow("Group into", self.subfolder_field)

        self.separate_box = QCheckBox(
            f"Keep unconverted MP4s in '{MP4_SUBFOLDER}/' and "
            f"uploadable files in '{COMMONS_SUBFOLDER}/'"
        )
        self.separate_box.setChecked(True)
        form.addRow("", self.separate_box)

        hint = StatusLabel(
            "Available tokens: {index} {programme} {title} {eventyay_id} "
            "{author} {room} {track} {date} {start} {end} {event}"
        )
        form.addRow("", hint)
        return group

    def _encoding_group(self) -> QGroupBox:
        group = QGroupBox("Encoding")
        form = QFormLayout(group)
        form.setLabelAlignment(Qt.AlignRight)

        self.format_box = QComboBox()
        for fmt in OutputFormat:
            self.format_box.addItem(fmt.label, fmt)
        self.format_box.currentIndexChanged.connect(self._format_changed)
        form.addRow("Format", self.format_box)

        self.format_hint = StatusLabel("")
        form.addRow("", self.format_hint)

        self.cut_box = QComboBox()
        self.cut_box.addItem("Accurate, fast seek (recommended)", CutMode.SMART)
        self.cut_box.addItem("Stream copy — instant, snaps to keyframes", CutMode.COPY)
        self.cut_box.addItem("Accurate, decode from the start — slowest", CutMode.REENCODE)
        self.cut_box.currentIndexChanged.connect(self._cut_mode_changed)
        form.addRow("Cutting", self.cut_box)

        self.cut_hint = StatusLabel("")
        form.addRow("", self.cut_hint)

        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(0, 63)
        self.quality_spin.setToolTip("Lower is better quality and a larger file.")
        form.addRow("Quality (CRF)", self.quality_spin)

        self.speed_spin = QSpinBox()
        self.speed_spin.setRange(0, 13)
        form.addRow("Encoder speed", self.speed_spin)
        self.speed_hint = StatusLabel("")
        form.addRow("", self.speed_hint)

        self.audio_field = QLineEdit()
        self.audio_field.setPlaceholderText("128k")
        form.addRow("Audio bitrate", self.audio_field)

        pads = QHBoxLayout()
        pads.setContentsMargins(0, 0, 0, 0)
        self.pad_start_spin = QSpinBox()
        self.pad_start_spin.setRange(0, 120)
        self.pad_start_spin.setSuffix(" s")
        self.pad_end_spin = QSpinBox()
        self.pad_end_spin.setRange(0, 120)
        self.pad_end_spin.setSuffix(" s")
        pads.addWidget(QLabel("before"))
        pads.addWidget(self.pad_start_spin)
        pads.addSpacing(12)
        pads.addWidget(QLabel("after"))
        pads.addWidget(self.pad_end_spin)
        pads.addStretch(1)
        pad_holder = QWidget()
        pad_holder.setLayout(pads)
        form.addRow("Extra time", pad_holder)

        self.extra_field = QLineEdit()
        self.extra_field.setPlaceholderText("extra ffmpeg arguments, e.g. -vf scale=1280:-2")
        form.addRow("Advanced", self.extra_field)

        self.overwrite_box = QCheckBox("Overwrite files that already exist")
        form.addRow("", self.overwrite_box)
        self.dry_run_box = QCheckBox("Dry run — show the commands without encoding")
        form.addRow("", self.dry_run_box)

        self.encoder_status = StatusLabel("")
        form.addRow("", self.encoder_status)
        return group

    def restyle(self) -> None:
        """Rebuild button icons after a theme change."""
        for button in self.findChildren(QPushButton):
            role = button.property("iconRole")
            if role:
                icons.apply(button, role)

    # -- settings ----------------------------------------------------------

    def _load_from_settings(self) -> None:
        settings = self.state.settings
        encoding = settings.encoding

        if settings.last_source and Path(settings.last_source).is_file():
            self.source_picker.field.setText(settings.last_source)
        if settings.last_csv and Path(settings.last_csv).is_file():
            self.csv_picker.field.setText(settings.last_csv)

        self.event_field.setText(settings.event_slug)
        self.offline_box.setChecked(settings.offline)
        self.output_picker.field.setText(settings.output_directory)
        self._output_is_automatic = not settings.output_directory
        self.filename_field.setText(settings.filename_template)
        self.subfolder_field.setText(settings.subfolder_template)
        self.separate_box.setChecked(settings.separate_by_format)

        index = self.format_box.findData(encoding.output_format)
        self.format_box.setCurrentIndex(max(0, index))
        index = self.cut_box.findData(encoding.cut_mode)
        self.cut_box.setCurrentIndex(max(0, index))

        self.quality_spin.setValue(encoding.crf)
        self.audio_field.setText(encoding.audio_bitrate)
        self.pad_start_spin.setValue(int(encoding.pad_start))
        self.pad_end_spin.setValue(int(encoding.pad_end))
        self.extra_field.setText(" ".join(encoding.extra_args))
        self.overwrite_box.setChecked(encoding.overwrite)
        self.dry_run_box.setChecked(settings.dry_run)

        self._format_changed()
        self._cut_mode_changed()
        self._check_encoders()

    def apply_to_settings(self) -> None:
        """Copy the form back into the shared settings object."""
        import shlex

        settings = self.state.settings
        encoding = settings.encoding

        settings.event_slug = self.event_field.text().strip()
        settings.offline = self.offline_box.isChecked()
        settings.output_directory = self.output_picker.path()
        settings.filename_template = (
            self.filename_field.text().strip() or "{index:02d}-{programme}"
        )
        settings.subfolder_template = self.subfolder_field.text().strip()
        settings.separate_by_format = self.separate_box.isChecked()
        settings.dry_run = self.dry_run_box.isChecked()

        fmt = _as_format(self.format_box.currentData())
        if fmt is not None and fmt is not encoding.output_format:
            settings.encoding = encoding = encoding.with_format(fmt)
        mode = _as_cut_mode(self.cut_box.currentData())
        if mode is not None:
            encoding.cut_mode = mode
        encoding.crf = self.quality_spin.value()
        encoding.audio_bitrate = self.audio_field.text().strip() or "128k"
        encoding.pad_start = float(self.pad_start_spin.value())
        encoding.pad_end = float(self.pad_end_spin.value())
        encoding.overwrite = self.overwrite_box.isChecked()
        try:
            encoding.extra_args = shlex.split(self.extra_field.text().strip())
        except ValueError:
            encoding.extra_args = []

        if encoding.video_codec == "libsvtav1":
            encoding.av1_preset = self.speed_spin.value()
        else:
            encoding.vp9_cpu_used = self.speed_spin.value()

        self.state.save_settings()

    # -- reactions ---------------------------------------------------------

    def _format_changed(self) -> None:
        fmt = _as_format(self.format_box.currentData())
        if fmt is None:
            return
        self.format_hint.show_message(
            fmt.hint, "warn" if not fmt.commons_compatible else "good"
        )

        from ..ffmpeg import FORMAT_DEFAULTS

        defaults = FORMAT_DEFAULTS[fmt]
        self.quality_spin.setValue(int(defaults["crf"]))
        self.audio_field.setText(str(defaults["audio_bitrate"]))

        if defaults["video_codec"] == "libsvtav1":
            self.speed_spin.setRange(0, 13)
            self.speed_spin.setValue(self.state.settings.encoding.av1_preset)
            self.speed_hint.show_message(
                "SVT-AV1 preset: 0 is slowest and smallest, 13 is fastest. "
                "8 is a good balance."
            )
        elif str(defaults["video_codec"]).startswith("libvpx"):
            self.speed_spin.setRange(0, 5)
            self.speed_spin.setValue(self.state.settings.encoding.vp9_cpu_used)
            self.speed_hint.show_message(
                "VP9 cpu-used: 0 is slowest and smallest, 5 is fastest."
            )
        else:
            self.speed_spin.setRange(0, 13)
            self.speed_hint.show_message("Not used by this encoder.")
            self.speed_spin.setEnabled(False)
            return
        self.speed_spin.setEnabled(True)

        if not fmt.commons_compatible and _as_cut_mode(self.cut_box.currentData()) is CutMode.COPY:
            self.cut_hint.show_message(
                "Stream copy is the fastest way to review cuts.", "info"
            )

    def _cut_mode_changed(self) -> None:
        mode = _as_cut_mode(self.cut_box.currentData())
        fmt = _as_format(self.format_box.currentData())
        if mode is CutMode.COPY and fmt is not None and not fmt.commons_compatible:
            self.cut_hint.show_message(
                "Clips can start up to several seconds early, on the tail of the "
                "previous session, because the cut snaps to the nearest keyframe.",
                "warn",
            )
        elif mode is CutMode.COPY:
            self.cut_hint.show_message(
                "Stream copy cannot change the codec, so this format will be "
                "re-encoded accurately instead.",
                "warn",
            )
        elif mode is CutMode.REENCODE:
            self.cut_hint.show_message(
                "Decodes the whole file up to each cut. Accurate, but slow on a "
                "long recording — the fast seek option is accurate too.",
                "warn",
            )
        else:
            self.cut_hint.show_message(
                "Seeks quickly to just before the cut, then decodes a few seconds "
                "to land on the exact frame.",
                "good",
            )

    def _check_encoders(self) -> None:
        encoder = resolve_av1_encoder(self.state.settings.ffmpeg_path)
        if encoder == "libsvtav1":
            self.encoder_status.show_message(f"FFmpeg AV1 encoder: {encoder}.", "good")
        elif encoder:
            self.encoder_status.show_message(
                f"Only '{encoder}' is available for AV1, which is much slower than "
                f"libsvtav1. Consider WebM (VP9) instead.",
                "warn",
            )
        else:
            self.encoder_status.show_message(
                "This FFmpeg build has no AV1 encoder. Use WebM (VP9) for Commons.",
                "warn",
            )

    def _source_chosen(self, path: str) -> None:
        path = path.strip()
        if not path:
            self.source_status.show_message("No video chosen yet.", "muted")
            self.state.set_source("", None)
            self.ready_changed.emit(self.is_ready())
            return
        if not Path(path).is_file():
            self.source_status.show_message(f"'{path}' does not exist.", "error")
            self.ready_changed.emit(self.is_ready())
            return

        self.source_status.show_message("Reading the video…", "muted")
        worker = ProbeWorker(path, self.state.settings.ffprobe_path)
        worker.signals.probed.connect(lambda info, p=path: self._probed(p, info))
        worker.signals.log.connect(self.state.log)
        start(worker)

    def _probed(self, path: str, info) -> None:
        if info is None:
            self.source_status.show_message(
                "FFmpeg could not read this file. Is it a video?", "error"
            )
            self.state.set_source("", None)
        else:
            self.state.set_source(path, info)
            self.source_status.show_message(
                f"{human_duration(info.duration)} · {info.resolution} · "
                f"{info.video_codec or '?'}/{info.audio_codec or 'no audio'} · "
                f"{human_size(info.size_bytes)}",
                "good",
            )
            self._suggest_output(path)
        self.ready_changed.emit(self.is_ready())

    def _suggest_output(self, source: str) -> None:
        """Put the clips beside the source video by default.

        The suggestion follows whichever video is chosen, but a folder the
        user picked themselves is never overwritten.
        """
        suggestion = str(Path(source).parent / f"{Path(source).stem}-clips")
        current = self.output_picker.path()
        if current and not self._output_is_automatic:
            return
        if current == suggestion:
            return

        self._output_is_automatic = True
        self._automatic_output = suggestion
        self.output_picker.field.setText(suggestion)
        self.state.settings.output_directory = suggestion
        self.output_status.show_message(
            "Chosen automatically from the video — change it if you want it "
            "somewhere else.",
            "muted",
        )
        self.ready_changed.emit(self.is_ready())

    def _csv_chosen(self, path: str) -> None:
        path = path.strip()
        if not path:
            self.csv_status.show_message("No timecode list loaded yet.", "muted")
            self.state.set_clips([])
            self.ready_changed.emit(self.is_ready())
            return
        if not Path(path).is_file():
            self.csv_status.show_message(f"'{path}' does not exist.", "error")
            self.ready_changed.emit(self.is_ready())
            return

        try:
            clips = read_clips(path)
        except (ValueError, OSError, UnicodeDecodeError) as exc:
            self.csv_status.show_message(str(exc), "error")
            self.state.set_clips([])
            self.ready_changed.emit(self.is_ready())
            return

        if not clips:
            self.csv_status.show_message("That file has no rows.", "warn")
            self.state.set_clips([])
            self.ready_changed.emit(self.is_ready())
            return

        self.state.csv_path = path
        self.state.settings.last_csv = path
        self.state.set_clips(clips)

        with_ids = sum(1 for clip in clips if clip.eventyay_id.strip())
        problems = sum(1 for clip in clips if clip.validate(self.state.source_duration or None))
        message = f"{len(clips)} clips · {with_ids} with a talk code"
        if problems:
            self.csv_status.show_message(
                f"{message} · {problems} need attention — check them on the next screen",
                "warn",
            )
        else:
            self.csv_status.show_message(message, "good")
        self.ready_changed.emit(self.is_ready())

    def _remember_event(self) -> None:
        self.state.settings.event_slug = self.event_field.text().strip()

    def _remember_output(self, path: str) -> None:
        # A path typed or browsed to by hand is the user's own choice, and
        # must survive picking a different source video.
        if path != self._automatic_output:
            self._output_is_automatic = False
            self.output_status.show_message("")
        self.state.settings.output_directory = path
        self.ready_changed.emit(self.is_ready())

    # -- schedule ----------------------------------------------------------

    def fetch_schedule(self, *, force: bool = False) -> None:
        event = self.event_field.text().strip()
        if not event:
            self.event_status.show_message(
                "Enter an event slug or schedule URL first.", "warn"
            )
            return

        self.event_status.show_message("Fetching the schedule…", "muted")
        settings = self.state.settings
        worker = ScheduleWorker(
            event,
            base_url=settings.base_url,
            organiser=settings.organiser,
            cache_ttl=settings.cache_ttl_seconds,
            offline=self.offline_box.isChecked(),
            force=force,
        )
        worker.signals.schedule_loaded.connect(self._schedule_loaded)
        start(worker)

    def _schedule_loaded(self, client, error) -> None:
        if error or client is None:
            self.state.set_schedule(None)
            self.event_status.show_message(str(error), "error")
            return

        self.state.set_schedule(client)
        info = client.info
        matched = sum(
            1 for clip in self.state.clips
            if clip.eventyay_id.strip() and client.get(clip.eventyay_id)
        )
        title = info.get("title") or client.event
        message = f"{title} — {len(client.sessions)} talks"
        if self.state.clips:
            message += f", {matched} of {len(self.state.clips)} clips matched"
        self.event_status.show_message(message, "good")

    # -- validity ----------------------------------------------------------

    def is_ready(self) -> bool:
        return bool(
            self.state.source_path
            and self.state.clips
            and self.output_picker.path()
        )
