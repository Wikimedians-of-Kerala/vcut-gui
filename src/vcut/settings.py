"""Persisted application settings.

Stored as JSON in the platform config directory so the CLI and the GUI see the
same values without the CLI having to depend on Qt.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .eventyay import DEFAULT_BASE_URL, DEFAULT_ORGANISER
from .ffmpeg import EncodingSettings, OutputFormat

APP_NAME = "vcut-gui"

#: Tokens accepted in :attr:`AppSettings.filename_template`.
FILENAME_TOKENS = (
    "{index}", "{programme}", "{title}", "{eventyay_id}", "{author}",
    "{start}", "{end}", "{duration}", "{room}", "{track}", "{date}", "{event}",
)


def config_directory() -> Path:
    """Per-user configuration directory, following platform convention."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    path = base / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_directory() -> Path:
    """Per-user cache directory, used for downloaded schedules."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    path = base / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings_path() -> Path:
    return config_directory() / "settings.json"


@dataclass
class AppSettings:
    """Everything the user can configure, beyond the per-run file choices."""

    # Output
    output_directory: str = ""
    filename_template: str = "{index:02d}-{programme}"
    subfolder_template: str = ""      # e.g. "{room}"; empty means a flat output dir
    slug_max_length: int = 80
    ascii_filenames: bool = False     # transliterate to ASCII for picky filesystems

    # Encoding
    encoding: EncodingSettings = field(default_factory=EncodingSettings)

    # Keep MP4 review cuts out of the folder holding Commons-ready files.
    separate_by_format: bool = True
    # Format produced by the convert step, when clips are cut to MP4 first.
    convert_format: OutputFormat = OutputFormat.WEBM_AV1

    # Processing
    parallel_jobs: int = 1
    dry_run: bool = False

    # Conference schedule
    event_slug: str = ""
    base_url: str = DEFAULT_BASE_URL
    organiser: str = DEFAULT_ORGANISER
    cache_ttl_hours: int = 24
    offline: bool = False
    auto_fetch_metadata: bool = True

    # Commons
    write_sidecars: bool = True
    commons_license: str = "{{Cc-by-sa-4.0}}"
    commons_categories: list[str] = field(default_factory=list)
    commons_template: str = ""        # empty means the built-in default template
    date_override: str = ""

    # Tools
    ffmpeg_path: str = ""
    ffprobe_path: str = ""

    # Recent choices, for convenience on the next launch
    last_source: str = ""
    last_csv: str = ""

    def to_dict(self) -> dict:
        data = asdict(self)
        data["encoding"] = self.encoding.to_dict()
        data["convert_format"] = self.convert_format.value
        return data

    @classmethod
    def from_dict(cls, data: dict) -> AppSettings:
        data = dict(data or {})
        encoding = EncodingSettings.from_dict(data.pop("encoding", {}) or {})
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        if "convert_format" in known:
            try:
                known["convert_format"] = OutputFormat(known["convert_format"])
            except ValueError:
                known["convert_format"] = OutputFormat.WEBM_AV1
        return cls(encoding=encoding, **known)

    @classmethod
    def load(cls, path: str | Path | None = None) -> AppSettings:
        target = Path(path) if path else settings_path()
        if not target.is_file():
            return cls()
        try:
            return cls.from_dict(json.loads(target.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            # A corrupt settings file should never stop the app from starting.
            return cls()

    def save(self, path: str | Path | None = None) -> None:
        target = Path(path) if path else settings_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        tmp.replace(target)  # atomic, so an interrupted save cannot corrupt it

    @property
    def cache_ttl_seconds(self) -> int:
        return max(0, int(self.cache_ttl_hours)) * 3600
