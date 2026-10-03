"""Manifest files written alongside the cut clips.

When clips are produced but not uploaded, the output folder needs to stand on
its own: someone picking it up later — or a future run of this tool — should be
able to tell what each file is, what it should be called on Commons, and what
description belongs to it, without re-reading the source CSV or re-fetching the
schedule.

Three files are written next to the clips:

``vcut-manifest.json``
    The complete record, including full wikitext. This is what a later upload
    run reads back.
``vcut-manifest.csv``
    The same thing as a spreadsheet, for eyeballing and for other tools.
``README.txt``
    Plain instructions for a human who opens the folder cold.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .commons import CommonsFile
from .models import Clip

MANIFEST_JSON = "vcut-manifest.json"
MANIFEST_CSV = "vcut-manifest.csv"
MANIFEST_README = "README.txt"

CSV_COLUMNS = (
    "file", "commons_filename", "uploadable", "programme", "eventyay_id",
    "author", "date", "start_time", "end_time", "duration", "source_url",
    "description_file", "warnings",
)


@dataclass
class ManifestEntry:
    """One clip's row in the manifest."""

    file: str = ""
    commons_filename: str = ""
    uploadable: bool = False
    programme: str = ""
    eventyay_id: str = ""
    author: str = ""
    date: str = ""
    start_time: str = ""
    end_time: str = ""
    duration: str = ""
    source_url: str = ""
    description_file: str = ""
    wikitext: str = ""
    warnings: list[str] = field(default_factory=list)
    uploaded: bool = False
    commons_url: str = ""

    def csv_row(self) -> dict:
        return {
            "file": self.file,
            "commons_filename": self.commons_filename,
            "uploadable": "yes" if self.uploadable else "no",
            "programme": self.programme,
            "eventyay_id": self.eventyay_id,
            "author": self.author,
            "date": self.date,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.duration,
            "source_url": self.source_url,
            "description_file": self.description_file,
            "warnings": "; ".join(self.warnings),
        }


def build_entry(
    clip: Clip,
    prepared: CommonsFile,
    *,
    session=None,
    base_directory: str | Path | None = None,
) -> ManifestEntry:
    """Describe one clip for the manifest."""
    from .models import format_timecode

    path = Path(prepared.local_path) if prepared.local_path else None
    relative = ""
    if path:
        relative = str(path)
        if base_directory:
            try:
                relative = str(path.relative_to(Path(base_directory)))
            except ValueError:
                relative = path.name

    try:
        duration = format_timecode(clip.duration)
    except Exception:  # noqa: BLE001 - an invalid row still belongs in the manifest
        duration = ""

    extension = path.suffix.lstrip(".").lower() if path else ""
    description_file = ""
    if path:
        sidecar = path.with_suffix(".txt")
        description_file = sidecar.name

    return ManifestEntry(
        file=relative,
        commons_filename=prepared.filename,
        uploadable=extension in {"webm", "ogv", "ogg", "mpg", "mpeg"},
        programme=(session.title if session else "") or clip.programme,
        eventyay_id=(session.code if session else "") or clip.eventyay_id,
        author=(session.author if session else "") or clip.author,
        date=(session.day if session else ""),
        start_time=clip.start_time,
        end_time=clip.end_time,
        duration=duration,
        source_url=(session.url if session else ""),
        description_file=description_file,
        wikitext=prepared.wikitext,
        warnings=list(prepared.warnings),
    )


def write_manifest(
    directory: str | Path,
    entries: list[ManifestEntry],
    *,
    event_info: dict | None = None,
    source_video: str = "",
) -> dict[str, Path]:
    """Write the manifest files into ``directory``.

    Returns a mapping of kind -> path for the files that were written.
    """
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    event_info = event_info or {}

    payload = {
        "generator": f"vcut-gui {__version__}",
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_video": source_video,
        "event": event_info,
        "clips": [
            {
                "file": entry.file,
                "commons_filename": entry.commons_filename,
                "uploadable": entry.uploadable,
                "programme": entry.programme,
                "eventyay_id": entry.eventyay_id,
                "author": entry.author,
                "date": entry.date,
                "start_time": entry.start_time,
                "end_time": entry.end_time,
                "duration": entry.duration,
                "source_url": entry.source_url,
                "description_file": entry.description_file,
                "wikitext": entry.wikitext,
                "warnings": entry.warnings,
                "uploaded": entry.uploaded,
                "commons_url": entry.commons_url,
            }
            for entry in entries
        ],
    }

    written: dict[str, Path] = {}

    json_path = target / MANIFEST_JSON
    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    written["json"] = json_path

    csv_path = target / MANIFEST_CSV
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CSV_COLUMNS))
        writer.writeheader()
        for entry in entries:
            writer.writerow(entry.csv_row())
    written["csv"] = csv_path

    readme_path = target / MANIFEST_README
    readme_path.write_text(_readme_text(entries, event_info), encoding="utf-8")
    written["readme"] = readme_path

    return written


def _readme_text(entries: list[ManifestEntry], event_info: dict) -> str:
    uploadable = [e for e in entries if e.uploadable]
    not_uploadable = [e for e in entries if not e.uploadable]

    lines = [
        f"{event_info.get('title') or 'Conference'} — session recordings",
        "=" * 60,
        "",
        f"Produced by vcut-gui {__version__} on "
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.",
        f"{len(entries)} clips: {len(uploadable)} ready for Wikimedia Commons, "
        f"{len(not_uploadable)} not.",
        "",
        "What is in this folder",
        "-" * 60,
        f"  {MANIFEST_JSON}   every clip's metadata and full file description",
        f"  {MANIFEST_CSV}    the same list as a spreadsheet",
        "  *.txt                the Commons file description for the video beside it",
        "",
    ]

    if not_uploadable:
        lines += [
            "Not yet uploadable",
            "-" * 60,
            "Wikimedia Commons does not accept MP4. These files must be converted",
            "to WebM before they can be uploaded:",
            "",
        ]
        lines += [f"  {entry.file}" for entry in not_uploadable[:20]]
        if len(not_uploadable) > 20:
            lines.append(f"  … and {len(not_uploadable) - 20} more")
        lines.append("")

    if uploadable:
        lines += [
            "Uploading later",
            "-" * 60,
            "Reopen this folder in vcut-gui and go to the upload screen, or upload",
            "by hand: each video's description is in the .txt file beside it, and",
            "the name to use on Commons is in the manifest.",
            "",
            "Files ready to upload:",
            "",
        ]
        for entry in uploadable[:20]:
            lines.append(f"  {entry.file}")
            lines.append(f"      -> {entry.commons_filename}")
        if len(uploadable) > 20:
            lines.append(f"  … and {len(uploadable) - 20} more")
        lines.append("")

    flagged = [e for e in entries if e.warnings]
    if flagged:
        lines += ["Needs attention", "-" * 60, ""]
        for entry in flagged[:20]:
            lines.append(f"  {entry.file or entry.programme}")
            for warning in entry.warnings:
                lines.append(f"      {warning}")
        lines.append("")

    return "\n".join(lines)


def read_manifest(directory: str | Path) -> dict | None:
    """Read a manifest back, so a later session can resume uploading."""
    path = Path(directory) / MANIFEST_JSON
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
