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

Video is drawn with libmpv's render API into a :class:`QOpenGLWidget`
(``vo=libmpv``), which is how VidCutter does it. The alternative -- handing
libmpv a native window id with ``wid`` -- is an X11 mechanism with no
Wayland equivalent, so it only worked by forcing the whole program through
XWayland. The render API embeds natively on Wayland, X11 and Windows alike.
Measured on a 2560x1440 AV1 recording under a Wayland session: 764 frames
in 25 s (the source is 30 fps) and exact seeks in 43 ms.

This class presents the slice of :class:`QMediaPlayer`'s interface the
screens actually use, so the two are interchangeable and Qt remains the
fallback when libmpv is not installed.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtOpenGLWidgets import QOpenGLWidget


def _add_bundled_library_to_path() -> None:
    """Let the Windows loader find the libmpv DLL shipped beside the program.

    python-mpv loads mpv-2.dll (or libmpv-2.dll) through the ordinary
    Windows search, which does not include the directory a frozen bundle
    unpacks into. Without this the packaged build cannot play anything, so
    the bundle's own directory goes on PATH before the import is tried.
    Does nothing anywhere else, or when running from a checkout.
    """
    import os
    import sys

    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return
    folder = os.path.dirname(sys.executable)
    if folder and folder not in os.environ.get("PATH", "").split(os.pathsep):
        os.environ["PATH"] = folder + os.pathsep + os.environ.get("PATH", "")


def available() -> bool:
    """Whether libmpv, its binding and the GL glue are all present."""
    _add_bundled_library_to_path()
    try:
        import mpv  # noqa: F401
        from OpenGL import GL  # noqa: F401
    except (ImportError, OSError):
        # OSError is what the binding raises when the shared library is
        # missing, which is a different failure from the module being absent.
        return False
    return True


def unavailable_reason() -> str:
    """Why libmpv cannot be used, for telling the user something useful."""
    _add_bundled_library_to_path()
    try:
        from OpenGL import GL  # noqa: F401
    except ImportError:
        return (
            "The PyOpenGL package is not installed. Install it with "
            "'pip install PyOpenGL' to play AV1 video."
        )
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


def _get_proc_address(_ctx, name):
    """Hand libmpv the address of a GL function, as its renderer requires."""
    from ctypes import c_char_p, c_void_p

    from OpenGL.platform import PLATFORM

    lookup = PLATFORM.getExtensionProcedure
    lookup.argtypes = [c_char_p]
    lookup.restype = c_void_p
    address = lookup(name)
    return int(address) if address else 0


class MpvSurface(QOpenGLWidget):
    """The widget libmpv draws video into.

    libmpv renders through the GL context this widget already owns, so the
    video lands inside the window on any platform Qt runs on -- no native
    window id, and so no X11 or XWayland requirement.
    """

    #: mpv signals a new frame from its own render thread. Qt widgets may
    #: only be touched on the GUI thread, so the request crosses over as a
    #: queued signal rather than a direct call.
    _frame_ready = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._context = None
        self._mpv = None
        self._on_ready = None
        self._frame_ready.connect(self.update, Qt.QueuedConnection)

    def attach(self, player_mpv, on_ready) -> None:
        """Bind an mpv instance, rendering as soon as GL is up.

        The GL context does not exist until Qt shows the widget, and the
        render context cannot be built before it, so loading a file waits
        for :meth:`initializeGL`.
        """
        self._mpv = player_mpv
        self._on_ready = on_ready
        if self._context is not None:
            # Already rendering -- a second file through the same widget,
            # which is what the clip player does when the chooser moves to
            # another clip. Nothing to build, so start it now.
            ready, self._on_ready = self._on_ready, None
            ready()
            return
        self._build_context()
        if self._context is None:
            # GL is not up yet. paintGL() builds the context on its first
            # run, which Qt schedules as soon as the widget is shown.
            self.update()

    def _build_context(self) -> None:
        """Create the render context, once there is both GL and an mpv.

        Qt calls initializeGL() when the widget is first shown, which may
        be either side of the player handing over its mpv instance, so this
        is driven from both and does nothing until both are in place.
        """
        if self._context is not None or self._mpv is None or not self.isValid():
            return

        import mpv

        # The callback has to be a ctypes function pointer: libmpv calls it
        # from C, and a plain Python function is rejected outright. Keep a
        # reference -- ctypes does not, and a collected callback crashes.
        self._proc_address = mpv.MpvGlGetProcAddressFn(_get_proc_address)
        try:
            self._context = mpv.MpvRenderContext(
                self._mpv,
                "opengl",
                opengl_init_params={"get_proc_address": self._proc_address},
            )
        except Exception:  # noqa: BLE001 - reported by the player, not here
            self._context = None
            return
        self._context.update_cb = self._frame_ready.emit
        if self._on_ready is not None:
            ready, self._on_ready = self._on_ready, None
            ready()

    def initializeGL(self) -> None:  # noqa: N802 - Qt's name
        self._build_context()

    def paintGL(self) -> None:  # noqa: N802 - Qt's name
        if self._context is None:
            # The GL context exists by the time Qt paints, so this is the
            # first moment the render context can be built when the file
            # was set before the widget was shown.
            self._build_context()
        if self._context is None:
            return
        # No glClear here: mpv paints every pixel of the viewport itself,
        # and PyOpenGL resolves its own context separately from Qt's, so a
        # clear through it fails with "invalid enumerant" on this path.
        ratio = self.devicePixelRatioF()
        self._context.render(
            flip_y=True,
            opengl_fbo={
                "w": int(self.width() * ratio),
                "h": int(self.height() * ratio),
                "fbo": self.defaultFramebufferObject(),
            },
        )

    def detach(self) -> None:
        """Drop the render context, before the mpv instance goes away."""
        context, self._context = self._context, None
        self._mpv = None
        self._on_ready = None
        if context is not None:
            context.update_cb = None
            try:
                context.free()
            except Exception:  # noqa: BLE001 - already gone is fine
                pass


class MpvPlayer(QObject):
    """libmpv behind the part of QMediaPlayer's interface the screens use."""

    #: Milliseconds, like QMediaPlayer, so the screens need no conversion.
    positionChanged = Signal(int)  # noqa: N815 - matches QMediaPlayer
    durationChanged = Signal(int)  # noqa: N815
    errorOccurred = Signal(object, str)  # noqa: N815

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._mpv = None
        self._surface: MpvSurface | None = None
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

    def set_surface(self, surface: "MpvSurface") -> None:
        """Render into the given :class:`MpvSurface`.

        Must be called before the first file is loaded: the render context
        is built on top of that widget's GL context.
        """
        self._surface = surface

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

        _add_bundled_library_to_path()
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
        if self._surface is not None:
            # Render through the widget's own GL context rather than taking
            # a window of our own, which is what keeps the video inside the
            # program on Wayland.
            options["vo"] = "libmpv"

        self._mpv = mpv.MPV(**options)
        return self._mpv

    # -- the QMediaPlayer-shaped interface ---------------------------------

    def setSource(self, url) -> None:  # noqa: N802 - matches QMediaPlayer
        path = url.toLocalFile() if hasattr(url, "toLocalFile") else str(url)
        self._source = path
        self._position_ms = 0
        self._duration_ms = 0
        self._pending_seek_ms = None
        # Tell the screen the old file is gone, so a stale duration and
        # playhead are not left on the transport while the next one loads.
        self.durationChanged.emit(0)
        self.positionChanged.emit(0)

        if not path:
            if self._mpv is not None:
                try:
                    self._mpv.command("stop")
                except Exception:  # noqa: BLE001 - nothing playing is fine
                    pass
            self._poll.stop()
            return

        try:
            player = self._ensure()
            if self._surface is not None:
                # The render context needs the widget's GL context, which Qt
                # only creates once the widget is shown. attach() starts the
                # file now if GL is already up, or as soon as it is.
                self._surface.attach(player, lambda: self._start(path))
            else:
                self._start(path)
        except Exception as exc:  # noqa: BLE001 - report, never raise
            self.errorOccurred.emit(None, f"libmpv could not open the file: {exc}")

    def _start(self, path: str) -> None:
        """Open the file, once there is somewhere to draw it."""
        if self._mpv is None:
            return
        try:
            self._mpv.play(path)
            # Paused on arrival, like QMediaPlayer: the screen decides when
            # to start, and a recording that plays itself is startling.
            self._mpv.pause = True
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
        # The render context points at the mpv instance, so it has to go
        # first or libmpv is left rendering into something freed.
        if self._surface is not None:
            self._surface.detach()
        if player is not None:
            try:
                player.terminate()
            except Exception:  # noqa: BLE001
                pass
