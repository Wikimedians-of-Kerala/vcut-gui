"""Reading and writing the clip list.

Real-world schedule exports vary: tab- or comma-separated, columns named
``programme``/``title``/``session``, ``start_time``/``start``/``in``. Rather than
demanding one exact shape, we sniff the dialect and map headers onto the fields
:class:`~vcut.models.Clip` understands.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

from .models import Clip

#: Canonical field -> header spellings we accept (compared case-insensitively,
#: ignoring spaces, hyphens and underscores).
COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "programme": ("programme", "program", "title", "session", "name", "roomname", "talk"),
    "start_time": ("starttime", "start", "begin", "in", "from", "startcode", "starttimecode"),
    "end_time": ("endtime", "end", "stop", "out", "to", "endcode", "endtimecode"),
    "eventyay_id": ("eventyayid", "eventid", "code", "talkcode", "id", "submissioncode"),
    "author": ("author", "authors", "speaker", "speakers", "presenter", "presenters"),
    "room": ("room", "roomname", "venue", "hall", "track"),
}

_CANONICAL = tuple(COLUMN_ALIASES)


def _normalise(header: str) -> str:
    return "".join(ch for ch in header.lower() if ch.isalnum())


def map_headers(headers: list[str]) -> dict[str, str]:
    """Map CSV headers onto canonical field names.

    Returns ``{header: canonical_field}``. Headers we do not recognise are left
    out and end up in :attr:`Clip.extra` so nothing from the input is lost.
    """
    mapping: dict[str, str] = {}
    claimed: set[str] = set()

    for header in headers:
        if header is None:
            continue
        norm = _normalise(header)
        for field_name in _CANONICAL:
            if field_name in claimed:
                continue
            if norm in COLUMN_ALIASES[field_name]:
                mapping[header] = field_name
                claimed.add(field_name)
                break
    return mapping


def sniff_dialect(sample: str) -> type[csv.Dialect] | csv.Dialect:
    """Detect the delimiter, falling back to comma when the sniffer is unsure."""
    try:
        return csv.Sniffer().sniff(sample, delimiters=",\t;|")
    except csv.Error:
        return csv.excel


def read_clips(path: str | Path, encoding: str = "utf-8-sig") -> list[Clip]:
    """Load clips from a delimited text file."""
    text = Path(path).read_text(encoding=encoding)
    return parse_clips(text)


def parse_clips(text: str) -> list[Clip]:
    """Parse clip rows from the text of a delimited file."""
    if not text.strip():
        return []

    dialect = sniff_dialect(text[:8192])
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    headers = reader.fieldnames or []
    mapping = map_headers(headers)

    if "start_time" not in mapping.values() or "end_time" not in mapping.values():
        raise ValueError(
            "CSV must have recognisable start and end time columns; "
            f"found headers: {', '.join(h for h in headers if h)}"
        )

    clips: list[Clip] = []
    for row in reader:
        if not any((value or "").strip() for value in row.values()):
            continue  # blank line

        clip = Clip()
        for header, value in row.items():
            if header is None:
                continue
            value = (value or "").strip()
            field_name = mapping.get(header)
            if field_name:
                setattr(clip, field_name, value)
            elif value:
                clip.extra[header] = value
        clips.append(clip)

    return clips


#: Columns written by :func:`write_clips`.
OUTPUT_COLUMNS = ("programme", "start_time", "end_time", "eventyay_id", "author", "room")


def write_clips(path: str | Path, clips: list[Clip], *, include_status: bool = False) -> None:
    """Write clips back out as a comma-separated file."""
    columns = list(OUTPUT_COLUMNS)
    if include_status:
        columns += ["status", "output_path", "message"]

    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        for clip in clips:
            row = [getattr(clip, name, "") for name in OUTPUT_COLUMNS]
            if include_status:
                row += [clip.status.value, clip.output_path, clip.message]
            writer.writerow(row)
