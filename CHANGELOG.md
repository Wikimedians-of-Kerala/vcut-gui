# Changelog

## Unreleased

- Keyboard shortcuts throughout, following what video editors have settled
  on: Space to play, J K L to shuttle, I and O to mark in and out, comma
  and full stop to step a frame. `Help > Keyboard shortcuts` (F1) lists
  them all, with a search box.

- Signing in to Wikimedia Commons from the app, with no terminal. A bot
  password is stored in the computer's keychain and the Pywikibot
  configuration written for you.
- Accounts with a passkey or two-factor sign-in can use the wiki's own login
  page in an embedded browser. A passkey is bound to the browser origin and
  cannot be typed into an app, so Commons answers it and the app takes the
  session afterwards — which it can then upload with directly.
- Hardware-accelerated encoding, detected by running each encoder rather
  than trusting what FFmpeg lists. The window says plainly what your GPU can
  do: most cannot encode AV1 or VP9, so they speed up MP4 review cuts while
  the Commons conversion stays on the processor.
- An FFmpeg settings window for the program paths, hardware acceleration,
  threading and raw arguments.
- Mono audio can be duplicated to both channels. Conference recordings are
  often a single mic feed, which players put in one ear.

## 1.0.2 — 2026-10-03

- The timeline zooms, with buttons, Ctrl+wheel, and *Zoom to clip*. At 1x a
  session in a nine-hour recording is a few pixels wide; zoomed in, cuts can
  be placed precisely. The playhead keeps itself in view while playing.
- Fixed the cell editor on the last row being drawn past the bottom of the
  table, over the buttons below, where it could not be read or used.
- Ready-made packages for Windows and Linux, with a Linux installer that
  adds a menu entry, and CI that builds both on a tag.
- INSTALL.md covers installing on each platform, including FFmpeg.

## 1.0.1 — 2026-10-03

- Projects: `File > Save project` stores the whole job in a `.vcut` file —
  clips, their state, settings, checked marks, and the Commons address of
  anything uploaded — so work can be picked up across days.
- Clips can be converted one at a time rather than only as an overnight
  batch, so a session can be converted, checked and uploaded in one sitting.
- The MP4 cut and the converted copy are now tracked separately, instead of
  the conversion replacing the original.
- Uploaded clips record their Commons address, are shown as already
  published, and are not offered for upload again.
- Table columns can be resized and reordered on every screen; previously
  most were fixed to their contents and could not be dragged at all.
- Dropdown arrows and spin box steppers are drawn explicitly: styling the
  controls stopped Qt drawing its own, leaving them looking like plain text
  fields.
- Clicking the timeline seeks there and selects the clip under the click.
- The output folder is suggested from the source video and follows it,
  unless you have chosen one yourself.
- `File > Video information` shows the full ffprobe detail.
- Fixed the wheel build, which failed on a duplicated logo entry.

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
