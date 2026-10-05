"""Playing video that Qt cannot decode.

Qt Multimedia carries its own FFmpeg build, and that build ships no AV1
decoder. AV1 is the format this program recommends for Commons, so its own
output is exactly what the built-in player shows as a black rectangle --
reporting that it is playing, with no error.

PyAV is a separate FFmpeg binding that does ship ``libdav1d``. Measured on
a 2560x1440 AV1 clip: 60 frames decoded in 0.15s, and 30 frames decoded and
scaled to RGB in 0.11s, so software decoding keeps up with playback easily.

Frames are decoded on a worker thread and handed to the GUI thread as
images. This is a preview, not an editing surface: it exists so a cut can
be eyeballed before upload.
"""

from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QImage, QPixmap


def available() -> bool:
    """Whether PyAV is installed."""
    import importlib.util

    return importlib.util.find_spec("av") is not None


def can_decode(codec: str) -> bool:
    """Whether PyAV has a decoder for this codec."""
    if not available():
        return False
    try:
        import av

        av.codec.Codec(codec, "r")
    except Exception:  # noqa: BLE001 - any failure means "no"
        return False
    return True


class Playback(QObject):
    """Decodes a file on a worker thread, emitting frames as pixmaps."""

    #: A frame to show, and the position it sits at in milliseconds.
    frame_ready = Signal(QPixmap, int)
    #: Total length in milliseconds, once known.
    duration_known = Signal(int)
    finished = Signal()
    failed = Signal(str)

    #: Frames are scaled down before they reach the GUI: a 1440p preview
    #: costs more to paint than it is worth, and the window is smaller than
    #: that anyway.
    MAX_WIDTH = 960

    #: Audio is resampled to this, which every sound card accepts.
    SAMPLE_RATE = 48000
    CHANNELS = 2

    def __init__(self, path: str | Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._path = Path(path)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._pause = threading.Event()
        self._seek_to: float | None = None
        self._lock = threading.Lock()
        self._audio_sink = None
        self._audio_device = None

    # -- control -----------------------------------------------------------

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._pause.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def pause(self) -> None:
        self._pause.set()

    def resume(self) -> None:
        self._pause.clear()

    def is_paused(self) -> bool:
        return self._pause.is_set()

    def seek(self, milliseconds: int) -> None:
        with self._lock:
            self._seek_to = max(0.0, milliseconds / 1000)
        # A seek while paused should show where it landed.
        self._pause.clear()

    def stop(self) -> None:
        self._stop.set()
        self._pause.clear()
        thread, self._thread = self._thread, None
        if thread is not None and thread.is_alive():
            thread.join(timeout=2)

    # -- audio -------------------------------------------------------------

    def _open_audio(self) -> None:
        """Open a sound device to push decoded samples to."""
        from PySide6.QtMultimedia import QAudioFormat, QAudioSink

        fmt = QAudioFormat()
        fmt.setSampleRate(self.SAMPLE_RATE)
        fmt.setChannelCount(self.CHANNELS)
        fmt.setSampleFormat(QAudioFormat.Int16)

        self._audio_sink = QAudioSink(fmt)
        self._audio_device = self._audio_sink.start()

    def _play_audio(self, frame, resampler) -> None:
        """Push one decoded audio frame to the sound device."""
        if self._audio_device is None or resampler is None:
            return
        try:
            for resampled in resampler.resample(frame):
                self._audio_device.write(bytes(resampled.planes[0]))
        except Exception:  # noqa: BLE001 - a silent preview beats a crash
            pass

    def _close_audio(self) -> None:
        sink, self._audio_sink = self._audio_sink, None
        self._audio_device = None
        if sink is not None:
            try:
                sink.stop()
            except RuntimeError:
                pass

    # -- the worker --------------------------------------------------------

    def _run(self) -> None:
        import time

        try:
            import av
        except ImportError:
            self.failed.emit("PyAV is not installed.")
            return

        try:
            container = av.open(str(self._path))
        except Exception as exc:  # noqa: BLE001 - av raises many types
            self.failed.emit(f"Could not open the file: {exc}")
            return

        try:
            stream = container.streams.video[0]
        except (IndexError, AttributeError):
            self.failed.emit("This file has no video track.")
            container.close()
            return

        stream.thread_type = "AUTO"
        if container.duration:
            self.duration_known.emit(int(container.duration / 1000))

        # Audio, when the file has any. Decoded in the same pass and pushed
        # to a Qt sink: a silent preview is not much use for checking that a
        # cut starts in the right place.
        audio_stream = None
        resampler = None
        try:
            if container.streams.audio:
                audio_stream = container.streams.audio[0]
                audio_stream.thread_type = "AUTO"
                resampler = av.AudioResampler(
                    format="s16", layout="stereo", rate=self.SAMPLE_RATE,
                )
                self._open_audio()
        except Exception:  # noqa: BLE001 - play silently rather than not at all
            audio_stream = None
            resampler = None

        width = min(self.MAX_WIDTH, stream.codec_context.width or self.MAX_WIDTH)
        height = 0
        if stream.codec_context.width:
            scale = width / stream.codec_context.width
            height = max(2, int(stream.codec_context.height * scale) // 2 * 2)

        started = time.monotonic()
        first_pts: float | None = None

        try:
            while not self._stop.is_set():
                with self._lock:
                    target, self._seek_to = self._seek_to, None
                if target is not None:
                    container.seek(
                        int(target / (stream.time_base or 1)), stream=stream
                    )
                    started = time.monotonic() - target
                    first_pts = 0.0

                streams = [stream] + ([audio_stream] if audio_stream else [])
                for frame in container.decode(*streams):
                    if audio_stream is not None and frame.__class__.__name__ == "AudioFrame":
                        self._play_audio(frame, resampler)
                        continue
                    if self._stop.is_set():
                        return
                    with self._lock:
                        if self._seek_to is not None:
                            break  # restart the outer loop at the new point

                    while self._pause.is_set() and not self._stop.is_set():
                        time.sleep(0.03)
                        started = time.monotonic() - (frame.time or 0)

                    seconds = float(frame.time or 0)
                    if first_pts is None:
                        first_pts = seconds
                        started = time.monotonic() - seconds

                    # Keep roughly to real time rather than decoding flat out.
                    ahead = seconds - (time.monotonic() - started)
                    if ahead > 0:
                        time.sleep(min(ahead, 0.5))

                    try:
                        rgb = frame.reformat(
                            width=width, height=height or None, format="rgb24"
                        )
                        plane = rgb.planes[0]
                        image = QImage(
                            bytes(plane), rgb.width, rgb.height,
                            plane.line_size, QImage.Format_RGB888,
                        ).copy()
                    except Exception:  # noqa: BLE001 - skip a bad frame
                        continue

                    self.frame_ready.emit(
                        QPixmap.fromImage(image), int(seconds * 1000)
                    )
                else:
                    break  # decoded to the end without a seek
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"Playback stopped: {exc}")
        finally:
            self._close_audio()
            container.close()

        if not self._stop.is_set():
            self.finished.emit()
