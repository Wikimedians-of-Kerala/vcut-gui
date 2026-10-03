"""Core domain types: timecodes, clips, and their validation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

_TIMECODE_RE = re.compile(
    r"""^\s*
    (?:(?P<h>\d+):)?        # optional hours
    (?P<m>[0-5]?\d):        # minutes
    (?P<s>[0-5]?\d)         # seconds
    (?:[.,](?P<frac>\d{1,6}))?  # optional fractional seconds
    \s*$""",
    re.VERBOSE,
)


class TimecodeError(ValueError):
    """Raised when a timecode string cannot be parsed."""


def parse_timecode(value: str) -> float:
    """Parse ``HH:MM:SS``, ``MM:SS`` or ``HH:MM:SS.sss`` into seconds.

    Bare numbers are treated as seconds so that "90" and "01:30" agree.
    """
    if value is None:
        raise TimecodeError("missing timecode")
    text = str(value).strip()
    if not text:
        raise TimecodeError("empty timecode")

    if re.fullmatch(r"\d+(?:[.,]\d+)?", text):
        return float(text.replace(",", "."))

    match = _TIMECODE_RE.match(text)
    if not match:
        raise TimecodeError(f"cannot parse timecode {value!r}")

    hours = int(match.group("h") or 0)
    minutes = int(match.group("m"))
    seconds = int(match.group("s"))
    frac = match.group("frac")
    total = hours * 3600 + minutes * 60 + seconds
    if frac:
        total += float(f"0.{frac}")
    return float(total)


def format_timecode(seconds: float, *, with_millis: bool = False) -> str:
    """Render seconds back to ``HH:MM:SS`` (or ``HH:MM:SS.mmm``)."""
    if seconds < 0:
        raise ValueError("cannot format a negative duration")
    whole = int(seconds)
    hours, remainder = divmod(whole, 3600)
    minutes, secs = divmod(remainder, 60)
    base = f"{hours:02d}:{minutes:02d}:{secs:02d}"
    if with_millis:
        millis = round((seconds - whole) * 1000)
        return f"{base}.{millis:03d}"
    return base


class ClipStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Clip:
    """One row of the CSV: a single session to be cut out of the source video."""

    programme: str = ""
    start_time: str = ""
    end_time: str = ""
    eventyay_id: str = ""
    author: str = ""
    room: str = ""

    selected: bool = True
    status: ClipStatus = ClipStatus.PENDING
    progress: float = 0.0
    message: str = ""
    output_path: str = ""
    #: Where the uploadable copy lives, once converted out of MP4.
    converted_path: str = ""
    #: Filled in once the clip reaches Commons, so a reopened project knows
    #: what has already been published and where it went.
    commons_filename: str = ""
    commons_url: str = ""
    uploaded_at: str = ""
    #: The description as last edited, kept so it survives a reopen.
    wikitext: str = ""
    # Metadata resolved from the conference schedule, when available.
    metadata: dict = field(default_factory=dict)
    # Columns present in the CSV that vcut does not model directly.
    extra: dict = field(default_factory=dict)

    @property
    def start_seconds(self) -> float:
        return parse_timecode(self.start_time)

    @property
    def end_seconds(self) -> float:
        return parse_timecode(self.end_time)

    @property
    def duration(self) -> float:
        return self.end_seconds - self.start_seconds

    def validate(self, source_duration: float | None = None) -> list[str]:
        """Return a list of human-readable problems; empty means the clip is usable."""
        problems: list[str] = []

        try:
            start = self.start_seconds
        except TimecodeError as exc:
            problems.append(f"start time: {exc}")
            start = None
        try:
            end = self.end_seconds
        except TimecodeError as exc:
            problems.append(f"end time: {exc}")
            end = None

        if start is not None and end is not None:
            if end <= start:
                problems.append("end time must be after start time")
            elif source_duration is not None:
                # A half-second of slack absorbs rounding in the probed duration.
                if start >= source_duration:
                    problems.append("start time is past the end of the source video")
                elif end > source_duration + 0.5:
                    problems.append(
                        f"end time exceeds source duration "
                        f"({format_timecode(source_duration)})"
                    )

        if not self.programme.strip():
            problems.append("programme title is empty")

        return problems

    @property
    def is_valid(self) -> bool:
        return not self.validate()

    @property
    def is_uploaded(self) -> bool:
        return bool(self.commons_url)

    @property
    def uploadable_path(self) -> str:
        """The file that would be uploaded: the converted copy if there is one."""
        return self.converted_path or self.output_path
