"""Turning clips into output file paths.

Two concerns live here: making a title safe for every filesystem we target, and
deciding which folder a clip lands in. Clips that are only cut (MP4) are kept
apart from clips that are converted for Commons (WebM/Ogg), so it is always
obvious which files are upload-ready.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from .ffmpeg import OutputFormat
from .models import Clip, format_timecode

#: Reserved device names on Windows; a file called "CON.mp4" cannot be created.
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

#: Characters Windows forbids outright, plus the path separators.
_ILLEGAL = r'<>:"/\|?*'

#: Subfolder names used when clips are not converted to a Commons format.
MP4_SUBFOLDER = "mp4-cuts"
COMMONS_SUBFOLDER = "commons-ready"


def slugify(text: str, *, max_length: int = 80, ascii_only: bool = False) -> str:
    """Make ``text`` safe as a filename component on Windows, macOS and Linux."""
    if not text:
        return ""

    text = unicodedata.normalize("NFC", str(text))
    if ascii_only:
        text = unicodedata.normalize("NFKD", text)
        text = text.encode("ascii", "ignore").decode("ascii")

    # Strip control characters and anything Windows rejects.
    text = "".join(" " if ch in _ILLEGAL else ch for ch in text if ord(ch) >= 32)
    text = re.sub(r"\s+", " ", text).strip()
    text = text.replace(" ", "-")
    text = re.sub(r"-{2,}", "-", text).strip("-._")

    if len(text) > max_length:
        # Prefer cutting at a separator so words stay whole.
        cut = text[:max_length]
        if "-" in cut[max_length // 2:]:
            cut = cut[: cut.rfind("-")]
        text = cut.strip("-._")

    if text.upper().split(".")[0] in _WINDOWS_RESERVED:
        text = f"_{text}"
    return text or "clip"


def token_values(clip: Clip, index: int, *, event: str = "") -> dict:
    """Values available to the filename and subfolder templates."""
    metadata = clip.metadata or {}

    def pick(*names: str, default: str = "") -> str:
        for name in names:
            value = metadata.get(name) or getattr(clip, name, "")
            if value:
                return str(value)
        return default

    try:
        duration = format_timecode(clip.duration).replace(":", "-")
    except (ValueError, Exception):  # noqa: BLE001 - invalid rows still need a name
        duration = ""

    return {
        "index": index,
        "programme": pick("title", "programme"),
        "title": pick("title", "programme"),
        "eventyay_id": pick("code", "eventyay_id"),
        "author": pick("author"),
        "room": pick("room"),
        "track": pick("track"),
        "date": pick("day", "date")[:10],
        "event": event,
        "start": (clip.start_time or "").replace(":", "-"),
        "end": (clip.end_time or "").replace(":", "-"),
        "duration": duration,
    }


def render_template(template: str, values: dict, *, max_length: int, ascii_only: bool) -> str:
    """Expand a filename template, slugifying each substituted value."""
    safe: dict = {}
    for key, value in values.items():
        if isinstance(value, int):
            safe[key] = value  # keep ints so "{index:02d}" still works
        else:
            safe[key] = slugify(str(value), max_length=max_length, ascii_only=ascii_only)
    try:
        rendered = template.format(**safe)
    except (KeyError, ValueError, IndexError):
        # An unusable template must not stop the run; fall back to a safe name.
        rendered = f"{values.get('index', 0):02d}-{safe.get('programme', 'clip')}"
    rendered = re.sub(r"-{2,}", "-", rendered).strip("-._ ")
    return rendered or f"clip-{values.get('index', 0)}"


def format_subfolder(fmt: OutputFormat, *, separate_unconverted: bool = True) -> str:
    """Child folder for a given output format.

    Keeping MP4 cuts out of the Commons folder means the upload step can point
    at one directory and be sure everything in it is actually uploadable.
    """
    if not separate_unconverted:
        return ""
    return MP4_SUBFOLDER if fmt is OutputFormat.MP4 else COMMONS_SUBFOLDER


def output_path(
    clip: Clip,
    index: int,
    output_directory: str | Path,
    *,
    fmt: OutputFormat = OutputFormat.MP4,
    filename_template: str = "{index:02d}-{programme}",
    subfolder_template: str = "",
    separate_by_format: bool = True,
    max_length: int = 80,
    ascii_only: bool = False,
    event: str = "",
) -> Path:
    """Build the full output path for one clip."""
    values = token_values(clip, index, event=event)
    stem = render_template(
        filename_template, values, max_length=max_length, ascii_only=ascii_only
    )

    directory = Path(output_directory)
    format_folder = format_subfolder(fmt, separate_unconverted=separate_by_format)
    if format_folder:
        directory = directory / format_folder
    if subfolder_template:
        sub = render_template(
            subfolder_template, values, max_length=max_length, ascii_only=ascii_only
        )
        if sub:
            directory = directory / sub

    return directory / f"{stem}.{fmt.extension}"


def unique_path(path: Path) -> Path:
    """Append ``-2``, ``-3`` … until the path does not already exist."""
    if not path.exists():
        return path
    stem, suffix, parent = path.stem, path.suffix, path.parent
    counter = 2
    while True:
        candidate = parent / f"{stem}-{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1
