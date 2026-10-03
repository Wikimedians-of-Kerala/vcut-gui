"""Saving and reopening a whole job as a single file.

Cutting a conference day is not one sitting: clips get verified, cut,
converted and uploaded over days, and the work has to survive closing the
app. A project file holds everything needed to pick it back up — the source
video, every clip with its state, the settings in force, and the Commons
address of anything already uploaded.

The format is JSON so it stays readable and diffable, and paths are stored
relative to the project file where possible, so a folder can be moved or
handed to someone else without breaking.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .models import Clip, ClipStatus
from .settings import AppSettings

PROJECT_SUFFIX = ".vcut"
#: Bumped only when older files would be read wrongly, never for additions.
FORMAT_VERSION = 1


class ProjectError(RuntimeError):
    """Raised when a project cannot be read."""


def _relative(path: str, base: Path) -> str:
    """Store a path relative to the project when it is sensible to do so."""
    if not path:
        return ""
    target = Path(path)
    try:
        return target.resolve().relative_to(base.resolve()).as_posix()
    except (ValueError, OSError):
        return target.as_posix()


def _absolute(stored: str, base: Path) -> str:
    if not stored:
        return ""
    candidate = Path(stored)
    if candidate.is_absolute():
        return str(candidate)
    return str((base / candidate).resolve())


@dataclass
class Project:
    """Everything about one cutting job."""

    source_path: str = ""
    csv_path: str = ""
    output_directory: str = ""
    event_slug: str = ""
    clips: list[Clip] = field(default_factory=list)
    settings: AppSettings | None = None
    verified: set[int] = field(default_factory=set)
    notes: str = ""
    created: str = ""
    modified: str = ""
    path: str = ""

    # -- saving ------------------------------------------------------------

    def to_dict(self, base: Path) -> dict:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return {
            "format": FORMAT_VERSION,
            "generator": f"vcut-gui {__version__}",
            "created": self.created or now,
            "modified": now,
            "source_path": _relative(self.source_path, base),
            "csv_path": _relative(self.csv_path, base),
            "output_directory": _relative(self.output_directory, base),
            "event_slug": self.event_slug,
            "notes": self.notes,
            "verified": sorted(self.verified),
            "settings": self.settings.to_dict() if self.settings else {},
            "clips": [self._clip_to_dict(clip, base) for clip in self.clips],
        }

    @staticmethod
    def _clip_to_dict(clip: Clip, base: Path) -> dict:
        return {
            "programme": clip.programme,
            "start_time": clip.start_time,
            "end_time": clip.end_time,
            "eventyay_id": clip.eventyay_id,
            "author": clip.author,
            "room": clip.room,
            "selected": clip.selected,
            "status": clip.status.value,
            "message": clip.message,
            "output_path": _relative(clip.output_path, base),
            # Where the converted, uploadable file lives, when it differs.
            "converted_path": _relative(clip.converted_path, base),
            "commons_filename": clip.commons_filename,
            "commons_url": clip.commons_url,
            "uploaded_at": clip.uploaded_at,
            "wikitext": clip.wikitext,
            "metadata": clip.metadata,
            "extra": clip.extra,
        }

    def save(self, path: str | Path) -> Path:
        target = Path(path)
        if target.suffix != PROJECT_SUFFIX:
            target = target.with_suffix(PROJECT_SUFFIX)
        base = target.parent
        base.mkdir(parents=True, exist_ok=True)

        payload = self.to_dict(base)
        # Write through a temporary file so an interrupted save cannot
        # destroy a project that took days to build up.
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(target)

        self.created = payload["created"]
        self.modified = payload["modified"]
        self.path = str(target)
        return target

    # -- loading -----------------------------------------------------------

    @classmethod
    def load(cls, path: str | Path) -> Project:
        source = Path(path)
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ProjectError(f"could not open {source.name}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ProjectError(f"{source.name} is not a valid project file: {exc}") from exc

        if not isinstance(payload, dict) or "clips" not in payload:
            raise ProjectError(f"{source.name} is not a vcut project file")

        stored_format = payload.get("format", 1)
        if stored_format > FORMAT_VERSION:
            raise ProjectError(
                f"{source.name} was written by a newer version of vcut "
                f"(format {stored_format}); update to open it"
            )

        base = source.parent
        project = cls(
            source_path=_absolute(payload.get("source_path", ""), base),
            csv_path=_absolute(payload.get("csv_path", ""), base),
            output_directory=_absolute(payload.get("output_directory", ""), base),
            event_slug=payload.get("event_slug", ""),
            notes=payload.get("notes", ""),
            verified=set(payload.get("verified", []) or []),
            created=payload.get("created", ""),
            modified=payload.get("modified", ""),
            path=str(source),
        )

        if payload.get("settings"):
            project.settings = AppSettings.from_dict(payload["settings"])

        for raw in payload.get("clips", []):
            project.clips.append(cls._clip_from_dict(raw, base))
        return project

    @staticmethod
    def _clip_from_dict(raw: dict, base: Path) -> Clip:
        clip = Clip(
            programme=raw.get("programme", ""),
            start_time=raw.get("start_time", ""),
            end_time=raw.get("end_time", ""),
            eventyay_id=raw.get("eventyay_id", ""),
            author=raw.get("author", ""),
            room=raw.get("room", ""),
            selected=bool(raw.get("selected", True)),
        )
        try:
            clip.status = ClipStatus(raw.get("status", "pending"))
        except ValueError:
            clip.status = ClipStatus.PENDING
        clip.message = raw.get("message", "")
        clip.output_path = _absolute(raw.get("output_path", ""), base)
        clip.converted_path = _absolute(raw.get("converted_path", ""), base)
        clip.commons_filename = raw.get("commons_filename", "")
        clip.commons_url = raw.get("commons_url", "")
        clip.uploaded_at = raw.get("uploaded_at", "")
        clip.wikitext = raw.get("wikitext", "")
        clip.metadata = raw.get("metadata", {}) or {}
        clip.extra = raw.get("extra", {}) or {}
        return clip

    # -- reporting ---------------------------------------------------------

    @property
    def uploaded_count(self) -> int:
        return sum(1 for clip in self.clips if clip.commons_url)

    @property
    def converted_count(self) -> int:
        return sum(1 for clip in self.clips if clip.converted_path)

    def summary(self) -> str:
        return (
            f"{len(self.clips)} clips · {self.converted_count} converted · "
            f"{self.uploaded_count} uploaded"
        )
