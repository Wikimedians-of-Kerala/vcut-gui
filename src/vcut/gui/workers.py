"""Background jobs.

Anything that touches the network, ffmpeg or Commons runs here on a worker
thread so the window keeps repainting. Workers communicate only through
signals; they never touch widgets.
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from ..commons import CommonsFile
from ..eventyay import ScheduleClient
from ..ffmpeg import (
    EncodingSettings,
    FFmpegError,
    build_command,
    convert_file,
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
                 dry_run: bool = False) -> None:
        super().__init__()
        self.signals = WorkerSignals()
        self._files = files
        self._comment = comment or "Uploading conference session recording"
        self._ignore_warnings = ignore_warnings
        self._dry_run = dry_run
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

        summary = f"{done} uploaded, {failed} failed"
        if self._cancelled:
            summary += " (cancelled)"
        self.signals.finished.emit(failed == 0 and not self._cancelled, summary)


def pool() -> QThreadPool:
    return QThreadPool.globalInstance()


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
