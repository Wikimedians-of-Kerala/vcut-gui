# vcut-gui

Cut a long conference recording into per-session video clips, fetch each
session's details from an Eventyay/pretalx schedule, generate Wikimedia
Commons file descriptions, and upload them.

Built for Wikimedia conference video teams. Runs on Windows and Linux.

## The four screens

**1. Set up** — pick the source video and the CSV of timecodes, point at the
conference schedule, and choose how to encode. The video is probed as soon as
it is chosen, so its length and codecs are visible before anything else.

**2. Verify and split** — the heart of it. A player sits beside the clip list:
selecting a row seeks to that clip's start, *Preview* plays the first few
seconds, and the transport bar steps a second or ten at a time. Any timecode
can be typed into *Go to* to jump straight there. Times can be edited in the
table or taken from the playhead with *Set start/end from player*. Clips can
be added, duplicated and removed, so sessions missing from the CSV are no
obstacle. Rows that cannot work — an end before its start, a time past the end
of the recording — are flagged before any encoding begins. *Split the video*
confirms what it is about to do, then shows progress per clip.

**3. Metadata** — each clip's details are looked up by talk code and the
Commons wikitext is generated and shown for editing. This is also where MP4
cuts are converted into an uploadable format.

**4. Upload** — review what will be sent, upload with Pywikibot, or save the
metadata into the folder and finish later.

Both long jobs — splitting and converting — confirm the work first, showing
the clip count, formats and an estimate, then run in a window that reports
overall progress, the file in hand, elapsed time and the time remaining.
Cancelling finishes the current clip rather than leaving a truncated file.

The window follows the desktop's light or dark theme, and the choice can be
forced under **View → Theme**.

## Requirements

- Python 3.11+
- [FFmpeg](https://ffmpeg.org/) on your `PATH`, built with `libsvtav1` (or
  `libvpx-vp9`) and `libopus` for Commons-ready output
- [Pywikibot](https://www.mediawiki.org/wiki/Manual:Pywikibot), only if you
  want to upload from the app

## Install

```sh
uv venv
uv pip install -e ".[dev]"
```

## Run

```sh
uv run vcut-gui
```

There is also a headless mode:

```sh
uv run vcut day1.mp4 sessions.csv -o clips --format webm-av1 --event india26
uv run vcut day1.mp4 sessions.csv -o clips --dry-run    # show the commands only
```

## Cutting accurately

Placing ffmpeg's `-ss` before `-i` seeks instantly but, when streams are
copied, snaps the cut to the preceding keyframe — so a talk can open several
seconds early, on the tail of the session before it. On a test file with
keyframes every ten seconds, a cut asking for 15 seconds produced 20.2.

The default **accurate, fast seek** avoids both problems: it seeks quickly to
shortly before the cut, then seeks accurately through the remainder. On a
twenty-minute file, cutting near the end took 0.11s against 1.06s for decoding
from the start, and both landed on the exact frame. The gap widens the longer
the recording.

| Mode | Speed | Accuracy |
| --- | --- | --- |
| Accurate, fast seek *(default)* | Fast | Exact |
| Stream copy | Instant | Snaps to keyframes |
| Decode from the start | Slow on long files | Exact |

## Video formats

Wikimedia Commons does not accept MP4. Uploads must be WebM, Ogg Theora or
MPEG, and [Commons recommends](https://commons.wikimedia.org/wiki/Commons:File_types#Video)
WebM with AV1 video and Opus audio.

| Format | Use |
| --- | --- |
| MP4 (H.264/AAC) | Fast local cuts for reviewing. **Cannot be uploaded.** |
| WebM (AV1/Opus) | Recommended for Commons: smallest, and the quickest of the three to encode. |
| WebM (VP9/Opus) | Larger and slower, but it is what Commons serves to viewers, so it plays without waiting on the transcode queue. |
| Ogg Theora | Legacy only; Commons advises against it for new uploads. |

On a 720p test clip, SVT-AV1 at preset 8 encoded about three times faster than
VP9 and produced a smaller file, so AV1 is both the recommendation and the
cheaper option. Commons builds its own VP9 versions for playback after upload.

Because AV1 and VP9 encoding is slow on a full day of sessions, the usual
workflow is to cut everything to MP4 first, check the cuts, and convert only
what is approved.

## Where the files go

```
clips/
├── mp4-cuts/            cut but not uploadable
├── commons-ready/       converted, with a .txt description beside each video
├── vcut-manifest.json   every clip's metadata and full description
├── vcut-manifest.csv    the same list as a spreadsheet
└── README.txt           what the folder holds and how to finish the upload
```

Keeping the two apart means the upload step can point at one folder and know
everything in it is uploadable. If you stop before uploading, the manifest and
descriptions are enough to finish later, by hand or by reopening the folder.

## CSV format

Tab- or comma-separated, with a header row:

```
programme	start_time	end_time	eventyay_id	author
Welcome and Opening Remarks	00:10:59	00:33:34	7NXGTK	Chinmayee Mishra
```

Only the start and end times are required. Column names are matched flexibly
(`title`/`session`/`programme`, `start`/`start_time`, and so on), and anything
unrecognised is carried through untouched. The `eventyay_id` is the talk code
used to look up metadata; rows without one still work and fall back to what the
CSV provides.

Two ready-made examples are in [examples/](examples/):
[`sample-schedule.tsv`](examples/sample-schedule.tsv) is a real day from
WikiConference India 2026 with talk codes, and
[`sample-minimal.csv`](examples/sample-minimal.csv) is the smallest list that
works. See [examples/README.md](examples/README.md) for the column reference.

## Conference schedules

The event can be given as a slug, an organiser path, or a full URL — all four
of these mean the same thing:

```
india26
wikicon/india26
https://wikimedia.eventyay.com/wikicon/india26/
https://wikimedia.eventyay.com/wikicon/india26/schedule/
```

The whole schedule is fetched once and cached, then looked up locally, which is
faster and kinder to the server than one request per clip. If the network is
down the cache is used, and offline mode skips the network entirely.

## Packaging

See [packaging/README.md](packaging/README.md).

## Tests

```sh
uv run pytest
```

The suite runs offline — the schedule tests use a recorded payload rather than
the network.

## Licence

[GNU GPL v3](https://www.gnu.org/licenses/gpl-3.0.en.html) or later.
