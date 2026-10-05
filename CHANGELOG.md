# Changelog

## 1.4.0 — 2026-10-05

Naming, licensing, and a home for the settings that had none.

### New

- **A Settings window**, under `File > Settings…`. Several options had no
  interface at all — the name patterns, subfolders, name length, ASCII
  transliteration, how long a fetched schedule is kept, offline mode, and
  the description files written beside each video. They are grouped by
  where a name is used: on Commons, or on disk.
- **A licence picker.** `Choose…` beside the licence box offers the ones a
  conference team reaches for — CC BY-SA 4.0 first as the Wikimedia
  default, then CC BY 4.0, CC0, the two older CC versions, and public
  domain. Each template was checked to exist on Commons, and each says what
  it means, since the difference between BY and BY-SA is the whole
  decision. Anything not listed can still be typed, which is how an
  event-specific permission template keeps working.
- **The schedule's talk code can be left out of Commons names.** It makes
  every name unique, which matters when two sessions share a title, but it
  means nothing to a reader who has never heard of pretalx.
- **Words can be joined with something other than a space.** Worth being
  plain about what this does: Commons stores titles with spaces and shows
  underscores only in addresses, and treats the two as the same character,
  so this changes how a name looks rather than how Commons files it.
- **An upload can replace an existing file as a new version.** A name
  already in use now raises its own error rather than a generic warning,
  because unlike every other failure there is something to offer.
- **The date override is a calendar**, not a text box: typing a date
  invites the wrong format and Commons wants ISO. A checkbox decides
  whether there is an override at all, since the usual answer is to take
  each clip's date from the schedule.

### Changed

- The Commons details panel is three compact rows rather than three sparse
  ones, recovering about 60px for the table underneath.
- Video information moved from File to View. It opens nothing and changes
  nothing.

### Fixed

- **The date picker was never styled.** `QDateEdit` was missing from the
  field rules, so it kept Qt's cramped defaults while every field beside it
  was taller. Its calendar button now gets the same panel a dropdown arrow
  has.
- **List rows had no padding**, so the licence text ran off the right edge.
  Rows now wrap, with the name in bold.
- **In light theme, unselected licence rows rendered blank.** A label inside
  an item widget is not reached by `QListWidget::item` rules and inherits
  nothing; the colours are now set from the palette directly. The selected
  row also kept its muted grey against a strong blue.
- **The cut-mode note never updated for MP4.** It was rebuilt after an early
  return that fires for any format without a speed setting — which is
  exactly the MP4 case where stream copy is the useful choice, so the screen
  claimed copying could not change the codec while offering the one format
  where it can.
- Turning the date override off left the date in place, because the refresh
  read `date_field.text()`, which on a calendar field is never empty.

## 1.3.0 — 2026-10-04

- **The Commons name can be typed, separately from the file on disk.** The
  name a file carries on Commons is often not the name it has locally: a
  talk title the generator truncated, or wording the community has settled
  on. The Commons name column is now editable, and the local file keeps its
  own name. Clearing the cell goes back to the generated name, and a
  hand-written one is shown in italics so it is visible which rows were
  changed. The extension always follows the real file rather than whatever
  was typed, since Commons refuses an upload whose name does not match the
  file — and the extension changes under you when a clip is converted from
  MP4 to WebM. The override is saved with the project.

## 1.2.0 — 2026-10-04

Uploading.

### Fixed

- **A browser sign-in was invisible to the upload screen.** Check reported
  "Not signed in to Commons yet" and Upload did nothing, while the login
  window said the same session could upload — the check asked Pywikibot and
  nothing else, so the only route an account with a passkey or two-factor
  sign-in has was never consulted. Either route now counts. A working bot
  password still wins, since it does not expire, but when neither works the
  expired session is reported rather than a generic "not signed in": it
  names the account and says what to do.

### New

- **Uploads show where each file landed.** The address on Commons has its
  own column, filled in as each file is accepted and shown for anything
  already published. It was recorded and logged before, which meant going
  looking for it. Double-clicking a row still opens the file.
- **Uploading gets a progress window**, the same one splitting and
  converting use: the account, the total size, how many files, and which one
  is in flight.
- **Files are marked as coming from vcut**, three ways, because they are
  different mechanisms. Every description carries
  `[[Category:Uploaded with vcut]]`, after the subject categories since
  those are what a reader wants first. The default edit summary is "Uploaded
  with vcut" on every route — previously the three disagreed and two did not
  name the tool. And the change tag `Vcut` is sent when Commons will accept
  it: a tag only exists once an administrator defines it at Special:Tags,
  and sending an undefined one fails the whole upload, so this is checked
  against the wiki once per session rather than assumed.

## 1.1.0 — 2026-10-04

Documentation, resource management, and the encoding fixes that came out of
cutting a real nine-hour conference recording.

### New

- **A help window**: `Help > How to use vcut`, or F1. Twelve topics covering
  each step, the timecode list, signing in, and what to do when something
  goes wrong. It opens on the topic for the screen you are looking at, and
  searches the body text as well as the headings, so "keyframe" finds the
  page that explains keyframes.
- **Two written guides**: [docs/GUIDE.md](docs/GUIDE.md) follows a day's
  recording from start to finish, and
  [docs/BUILDING.md](docs/BUILDING.md) covers building the Linux and
  Windows packages.
- **Encoding is budgeted against the machine.** Memory, cores and free disk
  are measured, and the per-encode cost with them: SVT-AV1 holds 950 MB at
  720p and 1.2 GB at 1080p, VP9 about a third of that. A computer with no
  room is told so before anything starts, with what to do about it, instead
  of starting a job the kernel will kill.
- **The player closes while encoding**, handing 86 MB to ffmpeg, and shows
  a grey panel saying why rather than going black. It reopens where it left
  off afterwards.
- **Stream copy now says what it costs on your file.** It is hundreds of
  times faster — 442 ms against 113 s for one 22-minute clip — and the note
  reports the real drift measured from the recording's own keyframes rather
  than warning vaguely about "several seconds".

### Fixed

Splitting and converting both failed on a long recording, in ways that gave
the user nothing to act on.

- **Converting to WebM failed with "ffmpeg exited with code -11".** With
  hardware acceleration on, an H.264 GPU encoder was used whatever the
  target format, so both AV1 and VP9 produced the same command: H.264 into
  a WebM container, which ffmpeg refuses outright. The requested codec was
  silently discarded. A hardware encoder is now used only when it produces
  the codec being asked for, so an H.264 GPU still accelerates MP4 cuts
  while WebM falls back to the software encoder. Measured afterwards on the
  same clip: VP9 125s, AV1 13.5s, both successful.
- **Splitting froze part-way through with the processor idle.** ffmpeg
  writes steadily to stderr, a pipe holds about 64 KB, and nothing drained
  it until the process had already exited — so ffmpeg blocked on its next
  write and the two waited on each other. A nine-hour source hit this every
  time, leaving a half-written file with no index. stderr is now drained
  while the job runs, and progress moved from a pipe to a file, which has no
  buffer to fill.
- **Pressing Convert for Commons crashed** with "'bool' object is not
  iterable": the button handed its checked state over as the list of rows.
- A failed run no longer leaves a 0-byte file behind. Every command carries
  `-n` so real work is never overwritten, which meant those leftovers
  blocked every retry until the folder was cleared by hand.
- A signal is explained rather than shown as a bare number: -11 now says
  ffmpeg crashed, -9 that it ran out of memory.

## 1.0.3 — 2026-10-04

- First release built by CI on GitHub, which is also the first Windows
  package built anywhere. Getting the first run green took four fixes: the
  PyInstaller spec called `TOC()` without importing it (it worked locally
  only because PyInstaller injects that name, and it is deprecated in
  PyInstaller 6); the build scripts took whatever interpreter `uv` found
  rather than the pinned one; the Windows self-test used the call operator
  on a GUI-subsystem binary, which PowerShell does not wait for, so a
  broken bundle could have passed its own check; and the actions were on a
  Node version GitHub is retiring.

- The project is on GitHub at
  [Wikimedians-of-Kerala/vcut-gui](https://github.com/Wikimedians-of-Kerala/vcut-gui),
  which is where the release packages are built. GitHub gives public
  repositories free Windows runners; GitLab's free tier has none, and the
  Windows `.exe` cannot be cross-compiled from Linux. Every address in the
  documentation, the packaging metadata and the Commons user agent now
  points there.

- A help window: `Help > How to use vcut`, or F1. Twelve topics covering
  each step, the timecode list, signing in, and what to do when something
  goes wrong. It opens on the topic for the screen you are looking at, and
  searches the text rather than only the headings, so looking for
  "keyframe" finds the page that explains keyframes.
- Two written guides: [docs/GUIDE.md](docs/GUIDE.md) follows a day's
  recording from start to finish, and [docs/BUILDING.md](docs/BUILDING.md)
  covers building the Linux and Windows packages.

- **The Linux package was carrying 119 MB of Chromium that could not run.**
  Excluding `QtWebEngineCore` alone stopped PyInstaller collecting
  Chromium's resource files while its shared libraries still arrived as
  transitive dependencies — so the download was 222 MB instead of 103 MB,
  and the application reported browser sign-in as available when it would
  have failed on use. Both are fixed: the exclusion is now complete, and
  the login window correctly offers a bot password instead.

- Keyboard shortcuts throughout, following what video editors have settled
  on: Space to play, J K L to shuttle, I and O to mark in and out, comma
  and full stop to step a frame. `Help > Keyboard shortcuts` (F1) lists
  them all, with a search box (`Ctrl+?`, or Shift+F1).

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
