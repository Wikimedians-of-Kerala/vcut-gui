"""Watching one cut clip.

The verify screen plays the whole nine-hour recording to find cut points.
This plays a single finished clip, which is a different question: did the
cut land where it should, and is this the file worth uploading?

A window rather than a panel on the metadata screen, for two reasons: the
screen has no room to spare beside the description editor, and a second
embedded player would hold a decoder open against the memory the encoder
wants.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..ffmpeg import probe
from ..models import format_timecode
from . import av_playback
from . import icons
from .theme import SPACE_EDGE, SPACE_ROW, SPACE_TIGHT
from .widgets import StatusLabel, human_size


#: Codecs Qt Multimedia cannot decode. Its bundled FFmpeg ships no AV1
#: decoder, while the system ffmpeg this program cuts with has three.
QT_CANNOT_DECODE = ("av1",)


def playable_here(path: str | Path) -> bool:
    """Whether this file can be shown in the built-in player.

    False means the desktop's own player should be used instead: a window
    that paints black and offers a button is a step nobody needs.
    """
    try:
        codec = (probe(path).video_codec or "").lower()
    except Exception:  # noqa: BLE001 - assume playable and let it try
        return True
    if codec not in QT_CANNOT_DECODE:
        return True
    return av_playback.can_decode(codec)


class ClipPlayerDialog(QDialog):
    """Play one clip from disk."""

    def __init__(self, path: str, title: str = "",
                 parent: QWidget | None = None,
                 clips: list | None = None, current: int = -1) -> None:
        super().__init__(parent)
        self._path = Path(path)
        self._playback: av_playback.Playback | None = None
        self.setWindowTitle(f"Playing — {self._path.name}")
        self.resize(760, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_EDGE, SPACE_ROW, SPACE_EDGE, SPACE_TIGHT)
        layout.setSpacing(SPACE_ROW)

        # A chooser, when the caller passed the whole list: checking a day of
        # cuts means moving between them, and closing the window for each one
        # would be tedious.
        self.chooser: QComboBox | None = None
        if clips:
            row = QHBoxLayout()
            row.setSpacing(SPACE_TIGHT)
            row.addWidget(QLabel("Clip"))

            self.chooser = QComboBox()
            for index, clip in enumerate(clips):
                name = clip.programme or f"Clip {index + 1}"
                playable = bool(clip.uploadable_path)
                self.chooser.addItem(
                    f"{index + 1:02d}. {name}" + ("" if playable else "  (not cut)"),
                    index,
                )
                if not playable:
                    # Still listed, so the gap in the day is visible.
                    model_item = self.chooser.model().item(index)
                    if model_item is not None:
                        model_item.setEnabled(False)
            if 0 <= current < self.chooser.count():
                self.chooser.setCurrentIndex(current)
            self.chooser.currentIndexChanged.connect(self._clip_chosen)
            row.addWidget(self.chooser, 1)
            layout.addLayout(row)
            self._clips = list(clips)
        else:
            self._clips = []
            if title:
                heading = QLabel(title)
                heading.setObjectName("screenHeading")
                heading.setWordWrap(True)
                layout.addWidget(heading)

        self.video = QVideoWidget()
        self.video.setMinimumSize(480, 270)
        self.video.setStyleSheet("background: #000;")
        self.video.setAspectRatioMode(Qt.KeepAspectRatio)

        # Where PyAV-decoded frames are painted, for codecs Qt cannot manage.
        self.frame_view = QLabel()
        self.frame_view.setMinimumSize(480, 270)
        self.frame_view.setAlignment(Qt.AlignCenter)
        self.frame_view.setStyleSheet("background: #000;")

        self.surface = QStackedWidget()
        self.surface.addWidget(self.video)
        self.surface.addWidget(self.frame_view)
        layout.addWidget(self.surface, 1)

        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video)
        self.player.positionChanged.connect(self._position_changed)
        self.player.durationChanged.connect(self._duration_changed)
        self.player.errorOccurred.connect(self._failed)

        transport = QHBoxLayout()
        transport.setSpacing(SPACE_TIGHT)

        self.play_button = QPushButton()
        self.play_button.setAutoDefault(False)
        icons.apply(self.play_button, "play")
        self.play_button.setProperty("iconRole", "play")
        self.play_button.clicked.connect(self._toggle)
        transport.addWidget(self.play_button)

        self.elapsed = QLabel("00:00:00")
        transport.addWidget(self.elapsed)

        self.scrubber = QSlider(Qt.Horizontal)
        self.scrubber.setRange(0, 0)
        self.scrubber.sliderMoved.connect(self._seek)
        transport.addWidget(self.scrubber, 1)

        self.total = QLabel("00:00:00")
        transport.addWidget(self.total)
        layout.addLayout(transport)

        self.status = StatusLabel("")
        layout.addWidget(self.status)

        # Shown only when the built-in player cannot manage the codec: the
        # desktop's own player almost certainly can.
        self.open_externally = QPushButton("Open in the system player")
        self.open_externally.setAutoDefault(False)
        self.open_externally.setVisible(False)
        self.open_externally.clicked.connect(self._open_externally)
        layout.addWidget(self.open_externally)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.accept)
        buttons.button(QDialogButtonBox.Close).clicked.connect(self.accept)
        layout.addWidget(buttons)

        self._open()

    def _clip_chosen(self, index: int) -> None:
        """Switch to another clip without closing the window."""
        if not (0 <= index < len(self._clips)):
            return
        clip = self._clips[index]
        path = clip.uploadable_path
        if not path:
            self.status.show_message(
                f"{clip.programme or 'This clip'} has not been cut yet.", "warn"
            )
            return

        self._release()
        self._path = Path(path)
        self.setWindowTitle(f"Playing — {self._path.name}")
        self.play_button.setEnabled(True)
        self.open_externally.setVisible(False)
        self._open()

    # -- playback ----------------------------------------------------------

    #: Codecs the bundled Qt cannot decode.
    #:
    #: Qt Multimedia carries its own FFmpeg, and that build ships no AV1
    #: decoder -- no libdav1d, no libaom -- while the FFmpeg this program
    #: cuts with has three. An AV1 clip therefore plays as a black
    #: rectangle, with the player reporting no error. Measured on the same
    #: three seconds of video: 0 frames as AV1, 87 as VP9 or H.264.
    #:
    #: These are decoded with PyAV instead, which does bundle libdav1d.
    QT_CANNOT_DECODE = ("av1",)

    def _open(self) -> None:
        if not self._path.is_file():
            self.status.show_message(
                f"{self._path.name} is not there yet — cut the clip first.",
                "error",
            )
            self.play_button.setEnabled(False)
            return

        size = human_size(self._path.stat().st_size)
        codec = self._codec()

        if codec in self.QT_CANNOT_DECODE:
            if av_playback.can_decode(codec):
                self.status.show_message(
                    f"{self._path.name} · {size} · {codec.upper()}, decoded "
                    f"in software", "muted",
                )
                self._play_with_pyav()
                return
            self.status.show_message(
                f"This clip is {codec.upper()}, which the built-in player "
                f"cannot decode. The file itself is fine: it plays in VLC or "
                f"a browser, and uploads to Commons normally.",
                "warn",
            )
            self.play_button.setEnabled(False)
            self.open_externally.setVisible(True)
            return

        self.surface.setCurrentWidget(self.video)
        self.status.show_message(f"{self._path.name} · {size}", "muted")
        self.player.setSource(QUrl.fromLocalFile(str(self._path)))
        self.player.play()
        self._sync_button()

    def _codec(self) -> str:
        try:
            return (probe(self._path).video_codec or "").lower()
        except Exception:  # noqa: BLE001 - a probe failure is not fatal
            return ""

    def _play_with_pyav(self) -> None:
        """Decode with PyAV and paint the frames ourselves."""
        self.surface.setCurrentWidget(self.frame_view)
        self._playback = av_playback.Playback(self._path, self)
        self._playback.frame_ready.connect(self._show_frame)
        self._playback.duration_known.connect(self._duration_changed)
        self._playback.failed.connect(self._failed)
        self._playback.finished.connect(self._sync_button)
        self._playback.start()
        self._sync_button()

    def _show_frame(self, pixmap, position_ms: int) -> None:
        self.frame_view.setPixmap(
            pixmap.scaled(
                self.frame_view.size(), Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        )
        self._position_changed(position_ms)

    def _toggle(self) -> None:
        if self._playback is not None:
            if self._playback.is_paused():
                self._playback.resume()
            else:
                self._playback.pause()
        elif self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()
        self._sync_button()

    def _sync_button(self) -> None:
        if self._playback is not None:
            playing = not self._playback.is_paused()
        else:
            playing = self.player.playbackState() == QMediaPlayer.PlayingState
        role = "pause" if playing else "play"
        icons.apply(self.play_button, role)
        self.play_button.setProperty("iconRole", role)

    def _seek(self, ms: int) -> None:
        if self._playback is not None:
            self._playback.seek(ms)
        else:
            self.player.setPosition(ms)

    def _position_changed(self, ms: int) -> None:
        if not self.scrubber.isSliderDown():
            self.scrubber.setValue(ms)
        self.elapsed.setText(format_timecode(ms / 1000))

    def _duration_changed(self, ms: int) -> None:
        self.scrubber.setRange(0, ms)
        self.total.setText(format_timecode(ms / 1000))

    def _failed(self, _error, message: str = "") -> None:
        self.status.show_message(
            message or "This file could not be played.", "error"
        )

    def _open_externally(self) -> None:
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._path)))

    # -- closing -----------------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: N802
        self._release()
        super().closeEvent(event)

    def accept(self) -> None:  # noqa: D102
        self._release()
        super().accept()

    def _release(self) -> None:
        """Let go of the file, so its decoder is not left holding memory."""
        if self._playback is not None:
            self._playback.stop()
            self._playback = None
        try:
            self.player.stop()
            self.player.setSource(QUrl())
        except RuntimeError:
            pass
