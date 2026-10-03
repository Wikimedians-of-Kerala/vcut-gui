# vcut-gui

Cut a long conference recording into per-session video clips, fetch each
session's metadata from an Eventyay/pretalx schedule, generate Wikimedia
Commons file descriptions, and upload them.

Built for Wikimedia conference video teams. Runs on Windows and Linux.

## Workflow

1. **Setup** — choose the source video, the CSV of timecodes, the conference
   event, and the encoding options.
2. **Verify** — step through each cut point in a video player and confirm the
   start and end times are right before anything is encoded.
3. **Metadata** — fetch each session's details from the schedule and review the
   generated Commons wikitext.
4. **Upload** — push the finished files to Wikimedia Commons with Pywikibot.

## Requirements

- Python 3.11+
- [FFmpeg](https://ffmpeg.org/) on your `PATH` (with `libsvtav1` and `libopus`
  for Commons-ready output)

## Install

```sh
uv venv
uv pip install -e ".[dev]"
```

## Run

```sh
uv run vcut-gui
```

## Video formats

Wikimedia Commons does not accept MP4. Uploads must be WebM, Ogg Theora or
MPEG, and [Commons recommends](https://commons.wikimedia.org/wiki/Commons:File_types#Video)
WebM with AV1 video and Opus audio.

| Format | Use |
| --- | --- |
| MP4 (H.264/AAC) | Fast local cuts for reviewing. **Cannot be uploaded.** |
| WebM (AV1/Opus) | Recommended for Commons: smallest and fastest to encode. |
| WebM (VP9/Opus) | Larger, but it is what Commons serves to viewers, so it plays before the transcode queue finishes. |
| Ogg Theora | Legacy only; Commons advises against it for new uploads. |

Clips that are only cut to MP4 are written to a `mp4-cuts/` subfolder, while
Commons-ready files go to `commons-ready/`, so it is always clear which files
are uploadable.

## CSV format

Tab- or comma-separated, with a header row:

```
programme	start_time	end_time	eventyay_id	author
Welcome and Opening Remarks	00:10:59	00:33:34	7NXGTK	Chinmayee Mishra
```

Only the start and end times are required. Column names are matched flexibly
(`title`/`session`/`programme`, `start`/`start_time`, and so on), and the
`eventyay_id` is the talk code used to look up metadata. Rows without a code
still work — they just use whatever the CSV provides.

## Licence

[GNU GPL v3](https://www.gnu.org/licenses/gpl-3.0.en.html) or later.
