"""A window showing everything ffprobe found about the source video.

The setup screen has room for one line of summary, which is enough to confirm
the right file is loaded but not enough to answer "will this cut cleanly?".
This shows the rest: the container, every stream, and the raw probe output for
when something unusual needs explaining.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..ffmpeg import MediaInfo
from .widgets import human_duration, human_size


def _fraction(value: str) -> str:
    """Render ffprobe's ``30000/1001`` style rates as a number."""
    try:
        numerator, _, denominator = str(value).partition("/")
        den = float(denominator or 1)
        if not den:
            return "—"
        rate = float(numerator) / den
        return f"{rate:.3f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return "—"


def _bitrate(value) -> str:
    try:
        rate = int(value)
    except (TypeError, ValueError):
        return "—"
    if rate >= 1_000_000:
        return f"{rate / 1_000_000:.2f} Mbps"
    return f"{rate / 1000:.0f} kbps"


class MediaInfoDialog(QDialog):
    """Everything known about the loaded source video."""

    def __init__(self, path: str, info: MediaInfo | None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Video information")
        self.resize(640, 560)
        self._path = path
        self._info = info

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(10)

        if info is None:
            layout.addWidget(QLabel("No video is loaded."))
            layout.addWidget(self._buttons(copyable=False))
            return

        name = QLabel(Path(path).name)
        name.setObjectName("screenHeading")
        name.setWordWrap(True)
        layout.addWidget(name)

        location = QLabel(str(Path(path).parent))
        location.setObjectName("screenSubheading")
        location.setWordWrap(True)
        location.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(location)

        tabs = QTabWidget()
        tabs.addTab(self._summary_tab(), "Summary")
        for index, stream in enumerate(info.streams("video")):
            tabs.addTab(self._stream_tab(stream, video=True),
                        "Video" if index == 0 else f"Video {index + 1}")
        for index, stream in enumerate(info.streams("audio")):
            tabs.addTab(self._stream_tab(stream, video=False),
                        "Audio" if index == 0 else f"Audio {index + 1}")
        tabs.addTab(self._raw_tab(), "Raw")
        layout.addWidget(tabs, 1)

        layout.addWidget(self._buttons())

    # -- tabs --------------------------------------------------------------

    def _scrolled_form(self, rows: list[tuple[str, str]], title: str = "") -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)

        box = QGroupBox(title) if title else QWidget()
        form = QFormLayout(box)
        form.setLabelAlignment(Qt.AlignRight)
        for label, value in rows:
            reading = QLabel(str(value) if value not in ("", None) else "—")
            reading.setTextInteractionFlags(Qt.TextSelectableByMouse)
            reading.setWordWrap(True)
            form.addRow(f"{label}", reading)

        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QScrollArea.NoFrame)
        area.setWidget(box)
        outer.addWidget(area)
        return page

    def _summary_tab(self) -> QWidget:
        info = self._info
        size = Path(self._path).stat().st_size if Path(self._path).is_file() else 0
        rows = [
            ("Duration", f"{human_duration(info.duration)}  ({info.duration:.3f} s)"),
            ("Container", info.format_name or "—"),
            ("File size", human_size(size or info.size_bytes)),
            ("Overall bitrate", _bitrate(info.bitrate)),
            ("Resolution", info.resolution),
            ("Frame rate", f"{info.fps:.3f}".rstrip("0").rstrip(".") + " fps"
             if info.fps else "—"),
            ("Video codec", info.video_codec or "—"),
            ("Audio codec", info.audio_codec or "no audio"),
            ("Streams", str(len(info.streams()))),
        ]
        return self._scrolled_form(rows, "The recording")

    def _stream_tab(self, stream: dict, *, video: bool) -> QWidget:
        common = [
            ("Codec", stream.get("codec_long_name") or stream.get("codec_name")),
            ("Profile", stream.get("profile")),
            ("Bitrate", _bitrate(stream.get("bit_rate"))),
            ("Duration", f"{float(stream.get('duration', 0) or 0):.3f} s"),
        ]
        if video:
            specific = [
                ("Resolution", f"{stream.get('width')}×{stream.get('height')}"),
                ("Display aspect", stream.get("display_aspect_ratio")),
                ("Pixel format", stream.get("pix_fmt")),
                ("Frame rate", f"{_fraction(stream.get('avg_frame_rate', ''))} fps"),
                ("Frames", stream.get("nb_frames")),
                ("B-frames", stream.get("has_b_frames")),
                ("Field order", stream.get("field_order")),
                ("Level", stream.get("level")),
            ]
        else:
            specific = [
                ("Sample rate", f"{stream.get('sample_rate')} Hz"),
                ("Channels", stream.get("channels")),
                ("Channel layout", stream.get("channel_layout")),
                ("Sample format", stream.get("sample_fmt")),
            ]
        return self._scrolled_form(common + specific, f"Stream {stream.get('index')}")

    def _raw_tab(self) -> QWidget:
        import json

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)

        view = QPlainTextEdit()
        view.setReadOnly(True)
        font = QFont("monospace")
        font.setStyleHint(QFont.TypeWriter)
        view.setFont(font)
        view.setPlainText(json.dumps(self._info.raw, indent=2))
        layout.addWidget(view)
        self._raw_text = view
        return page

    def _buttons(self, *, copyable: bool = True) -> QWidget:
        box = QDialogButtonBox()
        if copyable:
            copy = QPushButton("Copy details")
            copy.setAutoDefault(False)
            copy.clicked.connect(self._copy)
            box.addButton(copy, QDialogButtonBox.ActionRole)
        close = box.addButton(QDialogButtonBox.Close)
        close.setDefault(True)
        box.rejected.connect(self.reject)
        close.clicked.connect(self.accept)

        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(box)
        return holder

    def _copy(self) -> None:
        """Put the raw probe output on the clipboard, for bug reports."""
        import json

        QGuiApplication.clipboard().setText(json.dumps(self._info.raw, indent=2))
