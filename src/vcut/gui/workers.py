"""Background jobs.

Anything that touches the network, ffmpeg or Commons runs here on a worker
thread so the window keeps repainting. Workers communicate only through
signals; they never touch widgets.
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from .. import resources

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from ..commons import CommonsFile
from ..eventyay import ScheduleClient
from ..ffmpeg import (
    EncodingSettings,
    FFmpegError,
    build_command,
    convert_file,
    keyframe_interval,
    probe,
    run_command,
)


class WorkerSignals(QObject):
    """Signals shared by the workers below."""

    progress = Signal(int, float)      # row index, 0..1
    row_finished = Signal(int, bool, str)   # row index, succeeded, message
    log = Signal(str)
    finished = Signal(bool, str)       # whole job: succeeded, summary
    probed = Signal(object)            # MediaInfo
    schedule_loaded = Signal(object, object)  # ScheduleClient | None, error
    uploaded = Signal(int, str)        # row index, the name it got on Commons


class ProbeWorker(QRunnable):
    """Inspect a media file without blocking the window."""

    def __init__(self, path: str, ffprobe_path: str = "") -> None:
        super().__init__()
        self.signals = WorkerSignals()
        self._path = path
        self._ffprobe = ffprobe_path

    def run(self) -> None:
        try:
            info = probe(self._path, self._ffprobe)
        except (FFmpegError, ValueError) as exc:
            self.signals.log.emit(f"Could not read {self._path}: {exc}")
            self.signals.probed.emit(None)
            return

        # How far apart the keyframes are decides what stream copy costs in
        # accuracy, so measure it here rather than warning in the abstract.
        # Sampled a little way in: the opening of a recording is often an
        # idle slate, which is not representative.
        try:
            start_at = min(300.0, max(0.0, info.duration / 10))
            info.keyframe_interval = keyframe_interval(
                self._path, around=start_at, ffprobe_path=self._ffprobe
            )
        except Exception:  # noqa: BLE001 - never fail a probe over this
            pass

        self.signals.probed.emit(info)


class ScheduleWorker(QRunnable):
    """Fetch and index a conference schedule."""

    def __init__(self, event: str, *, base_url: str, organiser: str,
                 cache_ttl: int, offline: bool, force: bool = False) -> None:
        super().__init__()
        self.signals = WorkerSignals()
        self._event = event
        self._kwargs = {
            "base_url": base_url, "organiser": organiser,
            "cache_ttl": cache_ttl, "offline": offline,
        }
        self._force = force

    def run(self) -> None:
        try:
            client = ScheduleClient(self._event, **self._kwargs)
            client.load(force=self._force)
        except Exception as exc:  # noqa: BLE001 - surfaced in the UI
            self.signals.schedule_loaded.emit(None, str(exc))
            return
        self.signals.schedule_loaded.emit(client, None)


@dataclass
class CutJob:
    """One clip to cut."""

    index: int
    source: str
    output: str
    start: float
    end: float
    settings: EncodingSettings


class CutWorker(QRunnable):
    """Run a batch of cuts one after another, reporting per-row progress."""

    def __init__(self, jobs: list[CutJob], *, ffmpeg_path: str = "",
                 dry_run: bool = False) -> None:
        super().__init__()
        self.signals = WorkerSignals()
        self._jobs = jobs
        self._ffmpeg = ffmpeg_path
        self._dry_run = dry_run
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        # Budget against the job actually being run: AV1 at 1080p costs far
        # more than x264 at 720p, and the machine decides how many fit.
        first = self._jobs[0] if self._jobs else None
        codec = getattr(getattr(first, "settings", None), "video_codec", "")
        try:
            with encoding_slot(codec, **_budget_hints(self._jobs)):
                self._cut_all()
        except EncodingBusy as exc:
            self.signals.finished.emit(False, str(exc))

    def _cut_all(self) -> None:
        from pathlib import Path

        done = failed = 0
        for job in self._jobs:
            if self._cancelled:
                break
            try:
                Path(job.output).parent.mkdir(parents=True, exist_ok=True)
                command = build_command(
                    job.source, job.output, job.start, job.end, job.settings,
                    ffmpeg_path=self._ffmpeg,
                )
            except (FFmpegError, ValueError, OSError) as exc:
                failed += 1
                self.signals.row_finished.emit(job.index, False, str(exc))
                continue

            self.signals.log.emit(" ".join(command))
            if self._dry_run:
                self.signals.progress.emit(job.index, 1.0)
                self.signals.row_finished.emit(job.index, True, "dry run")
                done += 1
                continue

            try:
                code = run_command(
                    command, job.end - job.start,
                    on_progress=lambda value, i=job.index: self.signals.progress.emit(i, value),
                    on_log=self.signals.log.emit,
                    should_cancel=lambda: self._cancelled,
                )
            except FFmpegError as exc:
                failed += 1
                self.signals.row_finished.emit(job.index, False, str(exc))
                continue
            except Exception as exc:  # noqa: BLE001
                failed += 1
                self.signals.log.emit(traceback.format_exc())
                self.signals.row_finished.emit(job.index, False, str(exc))
                continue

            if self._cancelled:
                self.signals.row_finished.emit(job.index, False, "cancelled")
                break
            if code == 0:
                done += 1
                self.signals.row_finished.emit(job.index, True, "")
            else:
                failed += 1
                self.signals.row_finished.emit(
                    job.index, False, f"ffmpeg exited with code {code}"
                )

        summary = f"{done} finished, {failed} failed"
        if self._cancelled:
            summary += " (cancelled)"
        self.signals.finished.emit(failed == 0 and not self._cancelled, summary)


@dataclass
class ConvertJob:
    """One file to transcode into a Commons-ready format."""

    index: int
    source: str
    output: str
    settings: EncodingSettings
    duration: float = 0.0


class ConvertWorker(QRunnable):
    """Transcode already-cut clips into an uploadable format."""

    def __init__(self, jobs: list[ConvertJob], *, ffmpeg_path: str = "") -> None:
        super().__init__()
        self.signals = WorkerSignals()
        self._jobs = jobs
        self._ffmpeg = ffmpeg_path
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        # Budget against the job actually being run: AV1 at 1080p costs far
        # more than x264 at 720p, and the machine decides how many fit.
        first = self._jobs[0] if self._jobs else None
        codec = getattr(getattr(first, "settings", None), "video_codec", "")
        try:
            with encoding_slot(codec, **_budget_hints(self._jobs)):
                self._convert_all()
        except EncodingBusy as exc:
            self.signals.finished.emit(False, str(exc))

    def _convert_all(self) -> None:
        from pathlib import Path

        done = failed = 0
        for job in self._jobs:
            if self._cancelled:
                break
            try:
                Path(job.output).parent.mkdir(parents=True, exist_ok=True)
                code = convert_file(
                    job.source, job.output, job.settings,
                    ffmpeg_path=self._ffmpeg,
                    duration=job.duration or None,
                    on_progress=lambda v, i=job.index: self.signals.progress.emit(i, v),
                    on_log=self.signals.log.emit,
                    should_cancel=lambda: self._cancelled,
                )
            except (FFmpegError, OSError) as exc:
                failed += 1
                self.signals.row_finished.emit(job.index, False, str(exc))
                continue

            if self._cancelled:
                self.signals.row_finished.emit(job.index, False, "cancelled")
                break
            if code == 0:
                done += 1
                self.signals.row_finished.emit(job.index, True, "")
            else:
                failed += 1
                self.signals.row_finished.emit(
                    job.index, False, f"ffmpeg exited with code {code}"
                )

        summary = f"{done} converted, {failed} failed"
        if self._cancelled:
            summary += " (cancelled)"
        self.signals.finished.emit(failed == 0 and not self._cancelled, summary)


class UploadWorker(QRunnable):
    """Upload prepared files to Wikimedia Commons with Pywikibot."""

    def __init__(self, files: list[tuple[int, CommonsFile]], *,
                 comment: str = "", ignore_warnings: bool = False,
                 dry_run: bool = False, new_version: bool = False) -> None:
        super().__init__()
        self.signals = WorkerSignals()
        self._files = files
        self._comment = comment or "Uploading conference session recording"
        self._ignore_warnings = ignore_warnings
        self._dry_run = dry_run
        self._new_version = new_version
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        from ..upload import UploadError, upload_file

        done = failed = 0
        for index, prepared in self._files:
            if self._cancelled:
                break
            self.signals.progress.emit(index, 0.1)
            try:
                message = upload_file(
                    prepared,
                    comment=self._comment,
                    ignore_warnings=self._ignore_warnings,
                    dry_run=self._dry_run,
                    new_version=self._new_version,
                )
            except UploadError as exc:
                failed += 1
                self.signals.row_finished.emit(index, False, str(exc))
                continue
            except Exception as exc:  # noqa: BLE001
                failed += 1
                self.signals.log.emit(traceback.format_exc())
                self.signals.row_finished.emit(index, False, str(exc))
                continue

            done += 1
            self.signals.progress.emit(index, 1.0)
            self.signals.row_finished.emit(index, True, message)
            if not self._dry_run:
                self.signals.uploaded.emit(index, prepared.filename)

        summary = f"{done} uploaded, {failed} failed"
        if self._cancelled:
            summary += " (cancelled)"
        self.signals.finished.emit(failed == 0 and not self._cancelled, summary)


def pool() -> QThreadPool:
    return QThreadPool.globalInstance()


#: Called before an encoding job starts, so the window can release the media
#: player. Qt Multimedia loads its *own* FFmpeg into this process -- 7.1.5
#: against a system ffmpeg that may be 9.x -- and holding a large file open
#: through it while a child ffmpeg works on the same files has been
#: implicated in crashes that do not happen with the player idle.
_before_encoding: list = []


#: Called once the last encoding job finishes, so the window can take its
#: resources back.
_after_encoding: list = []


def before_encoding(callback) -> None:
    """Register something to run just before any encode starts."""
    if callback not in _before_encoding:
        _before_encoding.append(callback)


def after_encoding(callback) -> None:
    """Register something to run once the last encode finishes."""
    if callback not in _after_encoding:
        _after_encoding.append(callback)


def _restore_resources() -> None:
    for callback in list(_after_encoding):
        try:
            callback()
        except Exception:  # noqa: BLE001 - never fail a finished job
            pass


def _release_resources() -> None:
    for callback in list(_before_encoding):
        try:
            callback()
        except Exception:  # noqa: BLE001 - never block a job over this
            pass


#: How many encoding jobs may run at once, and who is running them.
#:
#: Encoding is the heaviest thing here: one SVT-AV1 encode of 720p holds
#: around 950 MB, measured. Start more than the machine can hold and the
#: kernel kills them, which arrives as "ffmpeg exited with code -11" and a
#: trail of 0-byte files. :mod:`vcut.resources` works out a safe number from
#: the memory and cores actually present, so a 64 GB workstation is allowed
#: more than a 4 GB laptop instead of everyone getting the same guess.
#:
#: Splitting and converting are both encoding, so they share this budget.
_encoding_guard = threading.Lock()
_encoding_running = 0
_encoding_allowed = 1


class EncodingBusy(RuntimeError):
    """Raised when there is no room to start another encoding job."""


def encoding_in_progress() -> bool:
    """Whether any encoding job is running."""
    with _encoding_guard:
        return _encoding_running > 0


def encoding_capacity() -> int:
    """How many jobs the last plan allowed to run at once."""
    with _encoding_guard:
        return _encoding_allowed


@contextmanager
def encoding_slot(
    codec: str = "",
    *,
    width: int = 0,
    height: int = 0,
    output_directory: str = ".",
) -> Iterator[None]:
    """Hold one encoding slot, or raise if the machine has no room.

    Non-blocking on purpose: a queued job that silently waits looks like a
    freeze, and the caller can say something useful instead.
    """
    global _encoding_running, _encoding_allowed

    budget = resources.plan(
        codec or "libsvtav1",
        width=width,
        height=height,
        wanted=1,
        output_directory=output_directory,
    )

    _release_resources()

    with _encoding_guard:
        if budget.blocked and _encoding_running == 0:
            # Nothing is running and still no room: the machine itself is
            # the problem, so pass on what it said to do about it.
            raise EncodingBusy(budget.blocked)
        _encoding_allowed = max(1, budget.jobs)
        if _encoding_running >= _encoding_allowed:
            raise EncodingBusy(
                f"Another encoding job is already running, and this computer "
                f"has room for {_encoding_allowed} at a time. Wait for it to "
                f"finish, or cancel it, before starting another."
            )
        _encoding_running += 1

    try:
        yield
    finally:
        with _encoding_guard:
            _encoding_running -= 1
            idle = _encoding_running == 0
        # Only once nothing is encoding: another job may still want the room.
        if idle:
            _restore_resources()


#: Workers handed to the thread pool are owned and deleted by it once they
#: finish. Their signal objects must outlive that, or queued signals are
#: dropped before the GUI thread delivers them — so keep a reference until the
#: worker reports that it is done.
_in_flight: set = set()


def start(worker) -> None:
    """Run a worker on the pool, keeping it alive until its signals arrive."""
    _in_flight.add(worker)

    def release(*_args) -> None:
        _in_flight.discard(worker)

    signals = worker.signals
    # Every worker ends with exactly one of these.
    for name in ("finished", "probed", "schedule_loaded"):
        signal = getattr(signals, name, None)
        if signal is not None:
            signal.connect(release)
    pool().start(worker)


def _budget_hints(jobs) -> dict:
    """What the resource planner needs to know about a batch of jobs.

    The size comes from the settings when they carry one; otherwise the
    planner falls back to its own assumption, which is deliberately on the
    heavy side.
    """
    from pathlib import Path

    width = height = 0
    output_directory = "."
    for job in jobs:
        settings = getattr(job, "settings", None)
        width = width or int(getattr(settings, "width", 0) or 0)
        height = height or int(getattr(settings, "height", 0) or 0)
        output = getattr(job, "output", "")
        if output and output_directory == ".":
            output_directory = str(Path(output).parent)
        if width and height:
            break
    return {
        "width": width,
        "height": height,
        "output_directory": output_directory,
    }
