"""Application state shared between the wizard screens.

The screens are deliberately thin: they read and write this object and emit
signals when something changes, so no screen needs to know about any other.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from ..commons import CommonsSettings
from ..eventyay import ScheduleClient, Session
from ..ffmpeg import MediaInfo, OutputFormat
from ..models import Clip
from ..settings import AppSettings


class AppState(QObject):
    """Everything the four screens share."""

    source_changed = Signal(str)
    clips_changed = Signal()
    clip_updated = Signal(int)
    schedule_changed = Signal()
    settings_changed = Signal()
    log_message = Signal(str)

    def __init__(self, settings: AppSettings | None = None) -> None:
        super().__init__()
        self.settings = settings or AppSettings.load()
        self.source_path: str = ""
        self.csv_path: str = ""
        self.media_info: MediaInfo | None = None
        self.clips: list[Clip] = []
        self.schedule: ScheduleClient | None = None
        self.event_info: dict = {}
        #: Where this job is saved, empty until it has been saved once.
        self.project_path: str = ""

    # -- source ------------------------------------------------------------

    def set_source(self, path: str, info: MediaInfo | None = None) -> None:
        self.source_path = path
        self.media_info = info
        self.settings.last_source = path
        self.source_changed.emit(path)

    @property
    def source_duration(self) -> float:
        return self.media_info.duration if self.media_info else 0.0

    # -- clips -------------------------------------------------------------

    def set_clips(self, clips: list[Clip]) -> None:
        self.clips = clips
        self.clips_changed.emit()

    def selected_clips(self) -> list[tuple[int, Clip]]:
        return [(i, c) for i, c in enumerate(self.clips) if c.selected]

    def validation_problems(self) -> dict[int, list[str]]:
        """Problems per clip index, for clips that have any."""
        problems = {}
        for index, clip in enumerate(self.clips):
            found = clip.validate(self.source_duration or None)
            if found:
                problems[index] = found
        return problems

    # -- schedule ----------------------------------------------------------

    def session_for(self, clip: Clip) -> Session | None:
        if not self.schedule:
            return None
        return self.schedule.get(clip.eventyay_id)

    def set_schedule(self, client: ScheduleClient | None) -> None:
        self.schedule = client
        self.event_info = client.info if client else {}
        self.schedule_changed.emit()

    # -- derived settings --------------------------------------------------

    def commons_settings(self) -> CommonsSettings:
        return self.settings.commons_settings()

    def output_format(self) -> OutputFormat:
        return self.settings.encoding.output_format

    def save_settings(self) -> None:
        self.settings.save()

    # -- projects ----------------------------------------------------------

    def to_project(self):
        """Capture the current job as a saveable project."""
        from ..project import Project

        return Project(
            source_path=self.source_path,
            csv_path=self.csv_path,
            output_directory=self.settings.output_directory,
            event_slug=self.settings.event_slug,
            clips=self.clips,
            settings=self.settings,
            path=self.project_path,
        )

    def load_project(self, project) -> None:
        """Replace the current job with a saved one."""
        if project.settings is not None:
            self.settings = project.settings
        if project.output_directory:
            self.settings.output_directory = project.output_directory
        if project.event_slug:
            self.settings.event_slug = project.event_slug

        self.project_path = project.path
        self.csv_path = project.csv_path
        self.clips = list(project.clips)

        # Re-probe rather than trusting a stored duration: the file may have
        # been moved, replaced or re-encoded since the project was saved.
        self.source_path = project.source_path
        self.media_info = None
        self.source_changed.emit(self.source_path)
        self.clips_changed.emit()
        self.settings_changed.emit()

    def log(self, message: str) -> None:
        self.log_message.emit(message)
