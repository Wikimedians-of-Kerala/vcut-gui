"""A video player backed by libmpv, for codecs Qt cannot decode.

Qt Multimedia carries its own FFmpeg build with no AV1 decoder compiled
in -- no libdav1d, no libaom-av1 -- so an AV1 recording plays as a black
rectangle with no error reported. That is fatal for the verify screen,
whose whole job is finding cut points by eye: without a picture there is
nothing to time against. AV1 is also the format this program recommends
for Commons, so its own output is what it cannot show.

libmpv is the player VidCutter and much else reaches for, and it uses the
system FFmpeg -- the same one already required here, which does have
libdav1d. Measured on a real AV1 file: plays it, and seeks to five minutes
in 34 ms.

This class presents the slice of :class:`QMediaPlayer`'s interface the
screens actually use, so the two are interchangeable and Qt remains the
fallback when libmpv is not installed.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal


def available() -> bool:
    """Whether libmpv and its binding are both present."""
    try:
        import mpv  # noqa: F401
    except (ImportError, OSError):
        # OSError is what the binding raises when the shared library is
        # missing, which is a different failure from the module being absent.
        return False
    return True


def unavailable_reason() -> str:
    """Why libmpv cannot be used, for telling the user something useful."""
    try:
        import mpv  # noqa: F401
    except ImportError:
        return (
            "The python-mpv package is not installed. Install it with "
            "'pip install python-mpv' to play AV1 video."
        )
    except OSError:
        return (
            "libmpv is not installed. On Debian or Ubuntu: "
            "'sudo apt install libmpv2'. On Windows, put mpv-2.dll beside "
            "the program."
        )
    return ""


class MpvPlayer(QObject):
    """libmpv behind the part of QMediaPlayer's interface the screens use."""

    #: Milliseconds, like QMediaPlayer, so the screens need no conversion.
    positionChanged = Signal(int)  # noqa: N815 - matches QMediaPlayer
    durationChanged = Signal(int)  # noqa: N815
    errorOccurred = Signal(object, str)  # noqa: N815

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._mpv = None
        self._window_id: int | None = None
        self._duration_ms = 0
        self._position_ms = 0
        self._source = ""
        self._pending_seek_ms: int | None = None

        # libmpv reports position on its own thread; polling on the GUI
        # thread keeps every signal where Qt wants it. 20 Hz is smooth
        # enough for a playhead and costs nothing.
        self._poll = QTimer(self)
        self._poll.setInterval(50)
        self._poll.timeout.connect(self._tick)

    # -- wiring ------------------------------------------------------------

    def set_surface(self, window_id: int) -> None:
        """Render into an existing native window.

        Must be called before the first file is loaded: libmpv binds its
        output window when it starts.
        """
        self._window_id = int(window_id)

    def _ensure(self):
        if self._mpv is not None:
            return self._mpv

        # libmpv refuses to run under anything but the C numeric locale and
        # aborts the whole process when it finds one -- "Non-C locale
        # detected. This is not supported." Qt sets the user's locale while
        # starting, so this has to be put back just before libmpv is
        # created. Only LC_NUMERIC: the rest of the locale is the user's and
        # affects how dates and text are shown.
        import locale

        locale.setlocale(locale.LC_NUMERIC, "C")

        import mpv

        options = {
            # Keep the last frame on screen when a file ends, rather than
            # going black: the verify screen is usually parked on a frame.
            "keep_open": "yes",
            # Exact seeking. The whole point here is landing on a frame, and
            # measured cost is tens of milliseconds.
            "hr_seek": "yes",
            "osc": False,
            "input_default_bindings": False,
            "input_vo_keyboard": False,
        }
        if self._window_id is not None:
            options["wid"] = str(self._window_id)

        self._mpv = mpv.MPV(**options)
        return self._mpv

    # -- the QMediaPlayer-shaped interface ---------------------------------

    def setSource(self, url) -> None:  # noqa: N802 - matches QMediaPlayer
        path = url.toLocalFile() if hasattr(url, "toLocalFile") else str(url)
        self._source = path
        self._position_ms = 0
        self._duration_ms = 0
        self._pending_seek_ms = None

        if not path:
            if self._mpv is not None:
                try:
                    self._mpv.command("stop")
                except Exception:  # noqa: BLE001 - nothing playing is fine
                    pass
            self._poll.stop()
            self.durationChanged.emit(0)
            self.positionChanged.emit(0)
            return

        try:
            player = self._ensure()
            player.play(path)
            # Paused on arrival, like QMediaPlayer: the screen decides when
            # to start, and a recording that plays itself is startling.
            player.pause = True
            self._poll.start()
        except Exception as exc:  # noqa: BLE001 - report, never raise
            self.errorOccurred.emit(None, f"libmpv could not open the file: {exc}")

    def source(self):
        from PySide6.QtCore import QUrl

        return QUrl.fromLocalFile(self._source) if self._source else QUrl()

    def play(self) -> None:
        if self._mpv is not None:
            self._mpv.pause = False
            self._poll.start()

    def pause(self) -> None:
        if self._mpv is not None:
            self._mpv.pause = True

    def stop(self) -> None:
        self._poll.stop()
        if self._mpv is None:
            return
        try:
            self._mpv.command("stop")
        except Exception:  # noqa: BLE001
            pass
        self._position_ms = 0
        self.positionChanged.emit(0)

    def position(self) -> int:
        return self._position_ms

    def duration(self) -> int:
        return self._duration_ms

    def setPosition(self, milliseconds: int) -> None:  # noqa: N802
        # A seek issued before the file has loaded is dropped by libmpv, so
        # remember it and apply it once the duration appears. This is what
        # restoring a position after an encode depends on -- without it the
        # user came back to the start of a nine-hour recording.
        if self._mpv is None or not self._duration_ms:
            self._pending_seek_ms = max(0, int(milliseconds))
            return
        target = max(0, int(milliseconds)) / 1000
        try:
            self._mpv.command("seek", target, "absolute", "exact")
            # Report immediately: a playhead that waits for the next poll
            # feels like a dropped click.
            self._position_ms = int(target * 1000)
            self.positionChanged.emit(self._position_ms)
        except Exception:  # noqa: BLE001 - a seek past the end is harmless
            pass

    def playbackState(self):  # noqa: N802
        from PySide6.QtMultimedia import QMediaPlayer

        if self._mpv is None or not self._source:
            return QMediaPlayer.StoppedState
        return (
            QMediaPlayer.PausedState if self._mpv.pause
            else QMediaPlayer.PlayingState
        )

    def setAudioOutput(self, _output) -> None:  # noqa: N802
        """Accepted and ignored: libmpv handles its own audio."""

    def setVideoOutput(self, _output) -> None:  # noqa: N802
        """Accepted and ignored: the surface is set with set_surface()."""

    # -- polling -----------------------------------------------------------

    def _tick(self) -> None:
        if self._mpv is None:
            return
        try:
            position = self._mpv.time_pos
            duration = self._mpv.duration
        except Exception:  # noqa: BLE001 - mid-load, properties are absent
            return

        if duration and int(duration * 1000) != self._duration_ms:
            self._duration_ms = int(duration * 1000)
            self.durationChanged.emit(self._duration_ms)
            # The file is open now, so a seek that arrived too early can go.
            pending, self._pending_seek_ms = self._pending_seek_ms, None
            if pending is not None:
                self.setPosition(pending)

        if position is not None:
            milliseconds = int(position * 1000)
            if milliseconds != self._position_ms:
                self._position_ms = milliseconds
                self.positionChanged.emit(milliseconds)

    # -- shutting down -----------------------------------------------------

    def release(self) -> None:
        """Let go of the file and the decoder."""
        self._poll.stop()
        player, self._mpv = self._mpv, None
        self._source = ""
        if player is not None:
            try:
                player.terminate()
            except Exception:  # noqa: BLE001
                pass
