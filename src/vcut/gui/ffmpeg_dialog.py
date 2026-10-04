"""A window for the FFmpeg settings that do not belong on the setup screen.

The setup screen carries the handful of choices every job needs. Everything
else — which binary to use, hardware acceleration, threading, and raw
arguments — lives here, so the common path stays short without hiding the
controls someone eventually needs.
"""

from __future__ import annotations

import shlex

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import hwaccel
from ..ffmpeg import FFmpegError, find_executable
from ..settings import AppSettings
from . import icons
from .widgets import FilePicker, StatusLabel, space_form


class FFmpegDialog(QDialog):
    """Everything about how FFmpeg is invoked."""

    settings_changed = Signal()

    def __init__(self, settings: AppSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("FFmpeg settings")
        self.resize(660, 620)
        self.settings = settings
        self._caps: hwaccel.Capabilities | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(12)

        tabs = QTabWidget()
        tabs.addTab(self._programs_tab(), "Programs")
        tabs.addTab(self._hardware_tab(), "Hardware")
        tabs.addTab(self._advanced_tab(), "Advanced")
        layout.addWidget(tabs, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Reset
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.Reset).clicked.connect(self._reset)
        layout.addWidget(buttons)

        self._load()
        self._show_cached_hardware()

    # -- tabs --------------------------------------------------------------

    def _programs_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(14)

        group = QGroupBox("Where FFmpeg lives")
        form = QFormLayout(group)
        space_form(form)

        self.ffmpeg_picker = FilePicker("leave empty to use the one on your PATH")
        form.addRow("ffmpeg", self.ffmpeg_picker)
        self.ffprobe_picker = FilePicker("leave empty to use the one on your PATH")
        form.addRow("ffprobe", self.ffprobe_picker)

        check = QPushButton("Check")
        check.setAutoDefault(False)
        icons.apply(check, "refresh")
        check.clicked.connect(self._check_programs)
        row = QHBoxLayout()
        row.addWidget(check)
        row.addStretch(1)
        holder = QWidget()
        holder.setLayout(row)
        form.addRow("", holder)

        self.program_status = StatusLabel("")
        form.addRow("", self.program_status)
        layout.addWidget(group)
        layout.addStretch(1)
        return page

    def _hardware_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        intro = QLabel(
            "A GPU encodes much faster than the processor, but only for the "
            "codecs its hardware implements. Wikimedia Commons accepts AV1, "
            "VP9 and Theora, and AV1 or VP9 encoders are still uncommon — so "
            "on many machines the GPU speeds up MP4 review cuts while the "
            "conversion for Commons stays on the processor."
        )
        intro.setWordWrap(True)
        intro.setObjectName("screenSubheading")
        layout.addWidget(intro)

        self.hardware_box = QCheckBox("Use the GPU when it can encode the chosen format")
        self.hardware_box.toggled.connect(self._hardware_toggled)
        layout.addWidget(self.hardware_box)

        group = QGroupBox("This machine")
        form = QFormLayout(group)
        space_form(form)

        self.encoder_box = QComboBox()
        form.addRow("Encoder", self.encoder_box)

        self.device_field = QLineEdit()
        self.device_field.setPlaceholderText("/dev/dri/renderD128")
        form.addRow("Device", self.device_field)

        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(0, 63)
        self.quality_spin.setToolTip(
            "Hardware encoders use a quantiser: lower is better quality and "
            "a larger file."
        )
        form.addRow("Quality", self.quality_spin)
        layout.addWidget(group)

        detect = QPushButton("Detect hardware")
        detect.setAutoDefault(False)
        icons.apply(detect, "refresh")
        detect.setToolTip("Try each encoder in turn and report which run")
        detect.clicked.connect(self._detect_hardware)
        row = QHBoxLayout()
        row.addWidget(detect)
        row.addStretch(1)
        layout.addLayout(row)

        self.hardware_status = StatusLabel("Not checked yet.")
        layout.addWidget(self.hardware_status)

        self.hardware_detail = QPlainTextEdit()
        self.hardware_detail.setReadOnly(True)
        self.hardware_detail.setMaximumHeight(150)
        self.hardware_detail.setPlaceholderText(
            "Detection results appear here, including why an encoder was "
            "rejected."
        )
        layout.addWidget(self.hardware_detail)
        return page

    def _advanced_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(14)

        group = QGroupBox("Processing")
        form = QFormLayout(group)
        space_form(form)

        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(0, 128)
        self.threads_spin.setSpecialValueText("automatic")
        self.threads_spin.setToolTip("0 lets FFmpeg decide, which is usually best.")
        form.addRow("Threads", self.threads_spin)

        self.parallel_spin = QSpinBox()
        self.parallel_spin.setRange(1, 16)
        self.parallel_spin.setToolTip(
            "Clips encoded at the same time. FFmpeg already uses every core, "
            "so more than one rarely helps."
        )
        form.addRow("Clips at once", self.parallel_spin)
        layout.addWidget(group)

        extra_group = QGroupBox("Extra arguments")
        extra_layout = QVBoxLayout(extra_group)
        note = QLabel(
            "Passed to FFmpeg before the output file, for anything this "
            "window does not cover. Quoted the way a shell would."
        )
        note.setWordWrap(True)
        note.setObjectName("screenSubheading")
        extra_layout.addWidget(note)

        self.extra_field = QLineEdit()
        self.extra_field.setPlaceholderText("-vf scale=1280:-2 -tune film")
        self.extra_field.textChanged.connect(self._validate_extra)
        extra_layout.addWidget(self.extra_field)

        self.extra_status = StatusLabel("")
        extra_layout.addWidget(self.extra_status)
        layout.addWidget(extra_group)
        layout.addStretch(1)
        return page

    # -- state -------------------------------------------------------------

    def _load(self) -> None:
        settings = self.settings
        encoding = settings.encoding
        self.ffmpeg_picker.field.setText(settings.ffmpeg_path)
        self.ffprobe_picker.field.setText(settings.ffprobe_path)
        self.hardware_box.setChecked(encoding.use_hardware)
        self.device_field.setText(encoding.hardware_device)
        self.quality_spin.setValue(encoding.hardware_quality)
        self.threads_spin.setValue(encoding.threads)
        self.parallel_spin.setValue(settings.parallel_jobs)
        self.extra_field.setText(" ".join(encoding.extra_args))
        self._hardware_toggled(encoding.use_hardware)

    def _reset(self) -> None:
        from ..ffmpeg import EncodingSettings

        defaults = EncodingSettings()
        self.hardware_box.setChecked(defaults.use_hardware)
        self.device_field.clear()
        self.quality_spin.setValue(defaults.hardware_quality)
        self.threads_spin.setValue(defaults.threads)
        self.parallel_spin.setValue(1)
        self.extra_field.clear()
        self.ffmpeg_picker.field.clear()
        self.ffprobe_picker.field.clear()

    def _accept(self) -> None:
        settings = self.settings
        encoding = settings.encoding
        settings.ffmpeg_path = self.ffmpeg_picker.path()
        settings.ffprobe_path = self.ffprobe_picker.path()
        settings.parallel_jobs = self.parallel_spin.value()

        encoding.use_hardware = self.hardware_box.isChecked()
        encoding.hardware_encoder = self.encoder_box.currentData() or ""
        encoding.hardware_device = self.device_field.text().strip()
        encoding.hardware_quality = self.quality_spin.value()
        encoding.threads = self.threads_spin.value()
        try:
            encoding.extra_args = shlex.split(self.extra_field.text().strip())
        except ValueError:
            encoding.extra_args = []

        settings.save()
        self.settings_changed.emit()
        self.accept()

    # -- actions -----------------------------------------------------------

    def _check_programs(self) -> None:
        import subprocess

        lines = []
        level = "good"
        for name, picker in (("ffmpeg", self.ffmpeg_picker),
                             ("ffprobe", self.ffprobe_picker)):
            try:
                exe = find_executable(name, picker.path())
            except FFmpegError as exc:
                lines.append(str(exc))
                level = "error"
                continue
            try:
                result = subprocess.run(
                    [exe, "-version"], capture_output=True, text=True, timeout=15,
                )
                first = result.stdout.splitlines()[0] if result.stdout else exe
            except (OSError, subprocess.TimeoutExpired, IndexError):
                first = exe
            lines.append(first)
        self.program_status.show_message(" · ".join(lines), level)

    def _hardware_toggled(self, enabled: bool) -> None:
        for widget in (self.encoder_box, self.device_field, self.quality_spin):
            widget.setEnabled(enabled)

    def _show_cached_hardware(self) -> None:
        caps = hwaccel.load_cached()
        if caps is None:
            self.hardware_status.show_message(
                "Not checked yet — press Detect hardware.", "muted"
            )
            return
        self._apply_capabilities(caps, from_cache=True)

    def _detect_hardware(self) -> None:
        self.hardware_status.show_message("Trying each encoder…", "info")
        self.hardware_detail.setPlainText("")
        from PySide6.QtWidgets import QApplication

        QApplication.processEvents()
        caps = hwaccel.detect(force=True, ffmpeg_path=self.ffmpeg_picker.path())
        self._apply_capabilities(caps)

    def _apply_capabilities(self, caps, *, from_cache: bool = False) -> None:
        self._caps = caps
        chosen = self.settings.encoding.hardware_encoder

        self.encoder_box.clear()
        for encoder in caps.working():
            suffix = "" if encoder.commons_ready else "  (not accepted by Commons)"
            self.encoder_box.addItem(f"{encoder.label}{suffix}", encoder.name)
        if not caps.working():
            self.encoder_box.addItem("No GPU encoder available", "")

        index = self.encoder_box.findData(chosen)
        if index >= 0:
            self.encoder_box.setCurrentIndex(index)

        if not self.device_field.text().strip() and caps.device:
            self.device_field.setPlaceholderText(caps.device)

        level = "good" if caps.commons_hardware else (
            "warn" if caps.any_hardware else "muted"
        )
        message = caps.summary()
        if from_cache:
            message += "  (remembered from an earlier check)"
        self.hardware_status.show_message(message, level)

        lines = []
        for encoder in caps.encoders:
            mark = "works" if encoder.works else "no"
            lines.append(f"{encoder.name:20} {mark:6} {encoder.detail}".rstrip())
        self.hardware_detail.setPlainText("\n".join(lines))

        self.hardware_box.setEnabled(caps.any_hardware)
        if not caps.any_hardware:
            self.hardware_box.setChecked(False)

    def _validate_extra(self, text: str) -> None:
        if not text.strip():
            self.extra_status.show_message("")
            return
        try:
            parts = shlex.split(text)
        except ValueError as exc:
            self.extra_status.show_message(f"Unbalanced quotes: {exc}", "error")
            return
        self.extra_status.show_message(
            f"{len(parts)} argument{'s' if len(parts) != 1 else ''}: "
            f"{' '.join(parts)}",
            "good",
        )
