"""Fetching session metadata from an Eventyay/pretalx schedule.

There is no per-talk REST endpoint on these instances, but the full schedule is
available as a single pretalx JSON export. We fetch that once, cache it on disk,
and index it by talk code — which is both faster and gentler on the server than
one request per clip.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import httpx

DEFAULT_BASE_URL = "https://wikimedia.eventyay.com"
DEFAULT_ORGANISER = "wikicon"
DEFAULT_CACHE_TTL = 24 * 3600  # seconds


class ScheduleError(RuntimeError):
    """Raised when a schedule cannot be fetched or parsed."""


@dataclass
class Session:
    """One talk from the conference schedule."""

    code: str = ""
    title: str = ""
    abstract: str = ""
    description: str = ""
    speakers: list[str] = field(default_factory=list)
    date: str = ""           # ISO datetime as published
    day: str = ""            # YYYY-MM-DD
    start: str = ""
    duration: str = ""
    room: str = ""
    track: str = ""
    language: str = "en"
    url: str = ""
    do_not_record: bool = False

    @property
    def author(self) -> str:
        return ", ".join(self.speakers)

    @property
    def full_description(self) -> str:
        """Abstract and description joined, as Commons descriptions want both."""
        parts = [p.strip() for p in (self.abstract, self.description) if p and p.strip()]
        return "\n\n".join(parts)


def parse_event_url(url: str) -> tuple[str, str, str]:
    """Split a schedule URL into ``(base_url, organiser, event_slug)``.

    Accepts anything from a bare slug to a full schedule URL, so users can paste
    whatever they have to hand::

        india26
        wikicon/india26
        https://wikimedia.eventyay.com/wikicon/india26/schedule/
    """
    text = (url or "").strip()
    if not text:
        raise ScheduleError("no event specified")

    if "://" in text:
        parsed = urlparse(text)
        base = f"{parsed.scheme}://{parsed.netloc}"
        parts = [p for p in parsed.path.split("/") if p]
    else:
        base = DEFAULT_BASE_URL
        parts = [p for p in text.split("/") if p]

    # Drop trailing path noise such as "schedule", "talk/XXXX" or "export/...".
    trimmed: list[str] = []
    for part in parts:
        if part in ("schedule", "talk", "speakers", "export", "p", "featured"):
            break
        trimmed.append(part)

    if not trimmed:
        raise ScheduleError(f"could not find an event slug in {url!r}")
    if len(trimmed) == 1:
        return base, DEFAULT_ORGANISER, trimmed[0]
    return base, trimmed[-2], trimmed[-1]


def schedule_url(base_url: str, organiser: str, event: str) -> str:
    return f"{base_url.rstrip('/')}/{organiser}/{event}/schedule/export/schedule.json"


def _cache_dir() -> Path:
    from .settings import cache_directory

    return cache_directory()


def _cache_path(organiser: str, event: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", f"{organiser}-{event}")
    return _cache_dir() / f"schedule-{safe}.json"


def fetch_schedule(
    event: str,
    *,
    base_url: str = DEFAULT_BASE_URL,
    organiser: str = DEFAULT_ORGANISER,
    cache_ttl: int = DEFAULT_CACHE_TTL,
    offline: bool = False,
    timeout: float = 30.0,
) -> dict:
    """Return the raw pretalx schedule payload, using the disk cache when fresh.

    Falls back to a stale cache if the network fails, so a flaky connection
    never blocks cutting.
    """
    if "://" in event or "/" in event:
        base_url, organiser, event = parse_event_url(event)

    cache_file = _cache_path(organiser, event)

    def read_cache() -> dict | None:
        if not cache_file.is_file():
            return None
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    if cache_file.is_file():
        age = time.time() - cache_file.stat().st_mtime
        if offline or age < cache_ttl:
            cached = read_cache()
            if cached is not None:
                return cached

    if offline:
        raise ScheduleError(
            f"offline mode is on and no cached schedule exists for {event!r}"
        )

    url = schedule_url(base_url, organiser, event)
    try:
        response = httpx.get(url, timeout=timeout, follow_redirects=True)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        stale = read_cache()
        if stale is not None:
            return stale
        raise ScheduleError(f"could not fetch the schedule from {url}: {exc}") from exc

    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        pass  # a cache we cannot write is not worth failing over

    return payload


def _text(value) -> str:
    """pretalx sometimes gives a plain string, sometimes ``{"en": "..."}``."""
    if isinstance(value, dict):
        return str(value.get("en") or next(iter(value.values()), "") or "")
    return "" if value is None else str(value)


def parse_sessions(payload: dict) -> dict[str, Session]:
    """Index a pretalx schedule payload by talk code."""
    conference = (payload or {}).get("schedule", {}).get("conference", {})
    sessions: dict[str, Session] = {}

    for day in conference.get("days", []):
        day_date = str(day.get("date", ""))[:10]
        for room_name, events in (day.get("rooms") or {}).items():
            for event in events or []:
                code = str(event.get("code") or "").strip()
                if not code:
                    continue  # breaks, registration and similar non-talks
                speakers = [
                    _text(person.get("public_name") or person.get("name"))
                    for person in event.get("persons", []) or []
                ]
                sessions[code.upper()] = Session(
                    code=code,
                    title=_text(event.get("title")),
                    abstract=_text(event.get("abstract")),
                    description=_text(event.get("description")),
                    speakers=[s for s in speakers if s],
                    date=_text(event.get("date")),
                    day=day_date,
                    start=_text(event.get("start")),
                    duration=_text(event.get("duration")),
                    room=_text(event.get("room")) or _text(room_name),
                    track=_text(event.get("track")),
                    language=_text(event.get("language")) or "en",
                    url=_text(event.get("url")) or _text(event.get("origin_url")),
                    do_not_record=bool(event.get("do_not_record")),
                )
    return sessions


def conference_info(payload: dict) -> dict:
    """Pull the conference-level fields used for defaults and display."""
    conference = (payload or {}).get("schedule", {}).get("conference", {})
    return {
        "title": _text(conference.get("title")),
        "acronym": _text(conference.get("acronym")),
        "start": _text(conference.get("start")),
        "end": _text(conference.get("end")),
        "timezone": _text(conference.get("time_zone_name")),
        "url": _text((payload or {}).get("schedule", {}).get("url")),
    }


class ScheduleClient:
    """Convenience wrapper holding one fetched schedule."""

    def __init__(
        self,
        event: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        organiser: str = DEFAULT_ORGANISER,
        cache_ttl: int = DEFAULT_CACHE_TTL,
        offline: bool = False,
    ) -> None:
        if "://" in event or "/" in event:
            base_url, organiser, event = parse_event_url(event)
        self.base_url = base_url
        self.organiser = organiser
        self.event = event
        self.cache_ttl = cache_ttl
        self.offline = offline
        self._payload: dict | None = None
        self._sessions: dict[str, Session] = {}

    def load(self, *, force: bool = False) -> dict[str, Session]:
        if self._payload is None or force:
            self._payload = fetch_schedule(
                self.event,
                base_url=self.base_url,
                organiser=self.organiser,
                cache_ttl=0 if force else self.cache_ttl,
                offline=self.offline,
            )
            self._sessions = parse_sessions(self._payload)
        return self._sessions

    @property
    def sessions(self) -> dict[str, Session]:
        return self._sessions or self.load()

    @property
    def info(self) -> dict:
        self.load()
        return conference_info(self._payload or {})

    def get(self, code: str) -> Session | None:
        if not code or not code.strip():
            return None
        return self.sessions.get(code.strip().upper())
