# Changelog

## 0.1.0 — 2026-10-03

First release.

### Cutting

- Cuts a long recording into per-session clips from a CSV or TSV of
  timecodes, with columns matched loosely so most exports work unchanged.
- Three cutting modes. The default seeks fast to just before the cut and then
  accurately through the remainder: frame-accurate, and about ten times
  quicker than decoding from the start of a long file. Plain stream copy is
  available but snaps to the preceding keyframe.
- Output formats for Wikimedia Commons — WebM (AV1/Opus), WebM (VP9/Opus) and
  Ogg Theora — plus MP4 for reviewing locally. Clips that are only cut are
  kept in `mp4-cuts/`, apart from the uploadable files in `commons-ready/`.
- Headless `vcut` command with the same engine.

### Verifying

- A player beside the clip list, with a full-width timeline marking every
  clip in dark blue and the selected one in orange.
- Clicking the timeline seeks there, and clicking a marked clip selects it.
- Clips can be added at the playhead, duplicated, removed and edited in
  place, and the list saved back out as a CSV.
- Timecodes can be typed, taken from the playhead, or jumped to directly.
- Rows that cannot work are flagged before any encoding starts.

### Metadata and upload

- Session details are fetched once from an Eventyay/pretalx schedule and
  cached, then looked up locally. The event is configurable, and a failed
  fetch falls back to the cache rather than blocking the cut.
- Commons `{{Information}}` wikitext is generated per clip and editable
  before saving, with the template itself configurable.
- Folders carry their own manifest, per-file descriptions and a README, so an
  upload can be finished later without the original CSV.
- Uploading through Pywikibot, dry-run by default.

### Interface

- Four-step window with the current step highlighted.
- Light and dark themes, following the desktop or chosen under View.
- Long jobs confirm what they will do, then report progress per clip with
  elapsed and remaining time.
- `File > Video information` shows the full ffprobe detail.

### Known limitations

- Uploading has been tested against validation and dry runs only; no files
  have been uploaded to Commons from this release.
- AV1 encoding runs around realtime, so a full conference day is an overnight
  job. Cut to MP4 first, review, then convert what you keep.
