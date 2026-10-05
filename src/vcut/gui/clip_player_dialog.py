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
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..ffmpeg import probe
from ..models import format_timecode
from .player_bar import RoundButton, transport_stylesheet
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
    from . import mpv_player

    # libmpv decodes everything the system ffmpeg does, AV1 included.
    if mpv_player.available():
        return True
    try:
        codec = (probe(path).video_codec or "").lower()
    except Exception:  # noqa: BLE001 - assume playable and let it try
        return True
    return codec not in QT_CANNOT_DECODE


class ClipPlayerDialog(QDialog):
    """Play one clip from disk."""

    def __init__(self, path: str, title: str = "",
                 parent: QWidget | None = None,
                 clips: list | None = None, current: int = -1) -> None:
        super().__init__(parent)
        self._path = Path(path)
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

        # libmpv when it is installed, Qt otherwise. Qt's bundled FFmpeg has
        # no AV1 decoder, and AV1 is what this program recommends for
        # Commons -- so without libmpv the player cannot show the very
        # clips it just produced.
        from . import mpv_player

        self.audio = QAudioOutput(self)
        if mpv_player.available():
            self.video = mpv_player.MpvSurface()
            self.video.setMinimumSize(480, 270)
            layout.addWidget(self.video, 1)
            self.player = mpv_player.MpvPlayer(self)
            self.player.set_surface(self.video)
        else:
            self.video = QVideoWidget()
            self.video.setMinimumSize(480, 270)
            self.video.setStyleSheet("background: #000;")
            self.video.setAspectRatioMode(Qt.KeepAspectRatio)
            layout.addWidget(self.video, 1)
            self.player = QMediaPlayer(self)
            self.player.setVideoOutput(self.video)
        self.player.setAudioOutput(self.audio)
        self.player.positionChanged.connect(self._position_changed)
        self.player.durationChanged.connect(self._duration_changed)
        self.player.errorOccurred.connect(self._failed)

        # The transport, as one panel: the same round buttons and styled
        # scrubber the verify screen uses, without its marking and zoom
        # controls, which mean nothing when watching a finished clip.
        bar = QFrame()
        bar.setObjectName("playerBar")
        bar.setAttribute(Qt.WA_StyledBackground, True)
        bar_layout = QVBoxLayout(bar)
        bar_layout.setContentsMargins(16, 12, 16, 12)
        bar_layout.setSpacing(10)

        scrub_row = QHBoxLayout()
        scrub_row.setSpacing(10)

        self.elapsed = QLabel("00:00:00")
        self.elapsed.setObjectName("playerTime")
        self.elapsed.setMinimumWidth(66)
        scrub_row.addWidget(self.elapsed)

        self.scrubber = QSlider(Qt.Horizontal)
        self.scrubber.setObjectName("playerScrubber")
        self.scrubber.setRange(0, 0)
        self.scrubber.sliderMoved.connect(self.player.setPosition)
        scrub_row.addWidget(self.scrubber, 1)

        self.total = QLabel("00:00:00")
        self.total.setObjectName("playerTime")
        self.total.setMinimumWidth(66)
        self.total.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        scrub_row.addWidget(self.total)
        bar_layout.addLayout(scrub_row)

        controls = QHBoxLayout()
        controls.setSpacing(SPACE_TIGHT)
        controls.addStretch(1)

        self.start_button = RoundButton("go-start", "Back to the start")
        self.start_button.clicked.connect(lambda: self.player.setPosition(0))
        controls.addWidget(self.start_button)

        self.back10_button = RoundButton("back10", "Back 10 seconds")
        self.back10_button.clicked.connect(lambda: self._nudge(-10_000))
        controls.addWidget(self.back10_button)

        self.back1_button = RoundButton("back1", "Back 1 second")
        self.back1_button.clicked.connect(lambda: self._nudge(-1000))
        controls.addWidget(self.back1_button)

        # Play is the one control that should be obvious at a glance.
        self.play_button = RoundButton(
            "play", "Play or pause", diameter=52, icon_size=30, primary=True
        )
        self.play_button.clicked.connect(self._toggle)
        controls.addSpacing(8)
        controls.addWidget(self.play_button)
        controls.addSpacing(8)

        self.forward1_button = RoundButton("forward1", "Forward 1 second")
        self.forward1_button.clicked.connect(lambda: self._nudge(1000))
        controls.addWidget(self.forward1_button)

        self.forward10_button = RoundButton("forward10", "Forward 10 seconds")
        self.forward10_button.clicked.connect(lambda: self._nudge(10_000))
        controls.addWidget(self.forward10_button)

        self.end_button = RoundButton("go-end", "Jump to the end")
        self.end_button.clicked.connect(self._goto_end)
        controls.addWidget(self.end_button)

        controls.addStretch(1)

        # Volume, at the right-hand end where a player usually keeps it.
        self.mute_button = RoundButton("volume", "Mute or unmute", diameter=28,
                                       icon_size=18)
        self.mute_button.clicked.connect(self._toggle_mute)
        controls.addWidget(self.mute_button)

        self.volume = QSlider(Qt.Horizontal)
        self.volume.setObjectName("playerScrubber")
        self.volume.setRange(0, 100)
        self.volume.setValue(100)
        self.volume.setFixedWidth(90)
        self.volume.setToolTip("Volume")
        self.volume.valueChanged.connect(self._volume_changed)
        controls.addWidget(self.volume)

        bar_layout.addLayout(controls)
        bar.setStyleSheet(transport_stylesheet())
        layout.addWidget(bar)

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
    #: No setting fixes this. Qt reports AV1 as decodable -- its format
    #: enum knows the codec exists -- and then delivers nothing, because
    #: its bundled libavcodec has no AV1 decoder compiled in. Forcing
    #: QT_MEDIA_BACKEND=ffmpeg, naming hardware device types, and trying a
    #: 320x180 file all gave 0 frames; the same content as VP9 gave 11.
    #:
    #: Decoding it in-process with PyAV was tried and abandoned: seeking
    #: and audio were both poor enough that handing the file to the
    #: desktop's own player is the better answer.
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

        if codec in self.QT_CANNOT_DECODE and not self._decodes_everything():
            self.status.show_message(
                f"This clip is {codec.upper()}, which the built-in player "
                f"cannot decode. The file itself is fine: it plays in VLC or "
                f"a browser, and uploads to Commons normally.",
                "warn",
            )
            self.play_button.setEnabled(False)
            self.open_externally.setVisible(True)
            return

        self.status.show_message(f"{self._path.name} · {size}", "muted")
        self.player.setSource(QUrl.fromLocalFile(str(self._path)))
        self.player.play()
        self._sync_button()

    def _codec(self) -> str:
        try:
            return (probe(self._path).video_codec or "").lower()
        except Exception:  # noqa: BLE001 - a probe failure is not fatal
            return ""

    def _decodes_everything(self) -> bool:
        """Whether the player in use can decode anything ffmpeg can."""
        from . import mpv_player

        return isinstance(self.player, mpv_player.MpvPlayer)

    def _toggle(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()
        self._sync_button()

    def _sync_button(self) -> None:
        playing = self.player.playbackState() == QMediaPlayer.PlayingState
        self.play_button.set_role("pause" if playing else "play")

    def _nudge(self, milliseconds: int) -> None:
        """Step forward or back, without running off either end."""
        target = self.player.position() + milliseconds
        self.player.setPosition(max(0, min(target, self.player.duration())))

    def _volume_changed(self, percent: int) -> None:
        """Set the volume on whichever player is in use."""
        setter = getattr(self.player, "set_volume", None)
        if setter is not None:          # libmpv
            setter(percent)
        else:                            # Qt wants 0.0-1.0
            self.audio.setVolume(percent / 100)
        if percent and self._is_muted():
            self._set_muted(False)
        self._sync_mute_button()

    def _toggle_mute(self) -> None:
        self._set_muted(not self._is_muted())
        self._sync_mute_button()

    def _is_muted(self) -> bool:
        getter = getattr(self.player, "is_muted", None)
        return getter() if getter is not None else self.audio.isMuted()

    def _set_muted(self, muted: bool) -> None:
        setter = getattr(self.player, "set_muted", None)
        if setter is not None:
            setter(muted)
        else:
            self.audio.setMuted(muted)

    def _sync_mute_button(self) -> None:
        silent = self._is_muted() or not self.volume.value()
        self.mute_button.set_role("volume-off" if silent else "volume")

    def _goto_end(self) -> None:
        """Jump to the last moment of the clip, not past it."""
        duration = self.player.duration()
        if duration:
            # A hair short of the end: seeking exactly to it leaves some
            # players with nothing to show.
            self.player.setPosition(max(0, duration - 200))

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
        self._shut_down()
        super().closeEvent(event)

    def accept(self) -> None:  # noqa: D102
        self._shut_down()
        super().accept()

    def _release(self) -> None:
        """Let go of the file, so its decoder is not left holding memory."""
        try:
            self.player.stop()
            self.player.setSource(QUrl())
        except RuntimeError:
            pass

    def _shut_down(self) -> None:
        """Release the file and, with libmpv, the decoder behind it.

        _release() is also used when switching clips, where the player is
        wanted again a moment later. This is the closing-the-window case,
        where the render context and the mpv instance should go too.
        """
        self._release()
        release = getattr(self.player, "release", None)
        if release is not None:
            try:
                release()
            except RuntimeError:
                pass
