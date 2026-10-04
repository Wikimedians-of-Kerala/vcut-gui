# Using vcut

How to take a day's conference recording and finish with session videos on
Wikimedia Commons.

This guide follows one job from start to end. If you only want to install the
program, see [INSTALL.md](../INSTALL.md); if you want to build the packages,
see [packaging/README.md](../packaging/README.md).

## Contents

- [Before you start](#before-you-start)
- [A day's work, start to finish](#a-days-work-start-to-finish)
- [Step 1 — Set up](#step-1--set-up)
- [Step 2 — Verify and split](#step-2--verify-and-split)
- [Step 3 — Metadata](#step-3--metadata)
- [Step 4 — Upload](#step-4--upload)
- [Signing in to Commons](#signing-in-to-commons)
- [Hardware acceleration](#hardware-acceleration)
- [Saving your work](#saving-your-work)
- [Finishing without uploading](#finishing-without-uploading)
- [When something goes wrong](#when-something-goes-wrong)

---

## Before you start

You need three things:

**The recording.** One video file covering the whole day or room. MP4 is
typical and is what the rest of this guide assumes.

**A list of timecodes.** A CSV or TSV saying where each session starts and
ends within that recording. The format is below, and two working examples are
in [examples/](../examples/).

**The conference's schedule address**, if you want session details filled in
automatically — for instance `india26`, or the full URL of the schedule page.
Without it you can still cut the video; you just type the titles yourself.

### The timecode list

Tab- or comma-separated, with a header row:

```
programme	start_time	end_time	eventyay_id	author
Welcome and Opening Remarks	00:10:59	00:33:34	7NXGTK	Chinmayee Mishra
Keynote: The Next Decade	00:35:02	01:21:40	BKQ3MF	Asha Menon
```

Only `start_time` and `end_time` are required. Column names are matched
loosely, so `title`, `session` and `programme` all work, as do `start` and
`start_time`. Columns the program does not recognise are carried through
untouched, so you can keep a `room` or `notes` column for yourself.

Times are `HH:MM:SS` — positions *within the recording*, not clock times. If
your schedule is in clock times, subtract the moment recording began.

`eventyay_id` is the talk code from the schedule, the short code in a talk's
URL. It is what links a clip to its session details. Rows without one still
work; they fall back to whatever the CSV says.

> **Tip** — Getting a few rows right matters more than getting all of them in.
> Sessions missing from the CSV can be added on screen 2, where you can see
> the video.

---

## A day's work, start to finish

A full conference day is usually done in two sittings, because converting
video for Commons is slow:

1. **Cut everything to MP4** (fast — minutes). Check the cuts while you watch.
2. **Convert and upload the approved clips** (slow — hours). Leave it running.

That is why MP4 is the default output. MP4 cannot be uploaded to Commons, but
it cuts almost instantly, which makes it the right format for checking your
work. Converting comes later, and only for the clips you approved.

Save the project between the two sittings and nothing is lost.

---

## Step 1 — Set up

Four things to fill in.

### The source video

Choose the recording. It is probed as soon as you pick it, and its length,
resolution, codecs and frame rate appear beneath. If something looks wrong
here — a duration of zero, no video stream — the file is the problem, and it
is better to find that out now than after cutting.

The output folder is filled in for you beside the video. Change it if you want
the clips elsewhere.

### The timecodes

Choose the CSV or TSV. The rows appear on screen 2.

### The conference schedule

Type the event as a slug, an organiser path, or a full URL. These all mean
the same thing:

```
india26
wikicon/india26
https://wikimedia.eventyay.com/wikicon/india26/
https://wikimedia.eventyay.com/wikicon/india26/schedule/
```

The whole schedule is fetched once and kept, then searched locally. That is
faster than one request per clip, and kinder to the server. If the network is
down the stored copy is used.

Leave it empty if the conference is not on Eventyay. You will type session
details yourself on screen 3.

### How to encode

Two choices matter.

**Cut accuracy** — leave this on *Accurate, fast seek*. The reason is in
[Cutting accurately](#cutting-accurately) below.

**Output format** — leave this on MP4 for the first pass, for the reason in
the section above.

Everything else about encoding lives in `File > FFmpeg settings`, including
hardware acceleration and the mono-to-stereo conversion.

---

## Step 2 — Verify and split

This is where the real work happens: confirming every cut point before
committing to an hours-long encode.

### The layout

The player sits beside the clip list, with the timeline across the full width
beneath them both. Every clip from your CSV is drawn on that timeline in dark
blue, and the one you have selected in orange. The shape of the day is visible
at a glance — and so is any gap where a session was missed.

### Checking a cut

Click a row and the player seeks to that clip's start. *Preview* plays the
opening seconds, which is usually enough to tell whether you have caught the
speaker's first words or the tail of the session before.

`Go to start` and `Go to end` jump to the two ends. The transport steps a
second (`J` / `L`) or ten (`Shift`+`←` / `→`) at a time, and `,` / `.` step a
single frame when you need to land exactly.

When a cut is right, press `V`: it marks the clip checked and moves to the
next one. Working down the list with `V` is the fastest way through a day.

### Fixing a cut

Three ways, in increasing order of precision:

- **Type it.** Edit the time in the table directly.
- **Take it from the playhead.** Park the playhead where the cut belongs and
  press `I` for the start or `O` for the end.
- **Zoom in first.** On a nine-hour recording a clip is a few pixels wide.
  The magnifier buttons — or `Ctrl`+mouse wheel — narrow the view around the
  playhead, and *Zoom to clip* fills the timeline with one session, which is
  what you want for trimming to the frame.

`Go to` accepts a typed timecode if you know where you are heading.

### Clips the CSV missed

*Add clip* makes a new row, *Duplicate* copies the selected one, and *Remove*
deletes it. A session the CSV never mentioned is no obstacle: find it in the
video, add a clip, and set both ends from the playhead.

### Rows that cannot work

An end before its start, or a time past the end of the recording, is flagged
before any encoding begins. Fix the flagged rows — the split will not start
while any remain.

### Splitting

*Split the video* shows what it is about to do — how many clips, to what
format, where they will go — and asks you to confirm. Then it runs, reporting
progress per clip, the file in hand, elapsed time and time remaining.

Cancelling finishes the clip it is on rather than leaving a truncated file.

---

## Step 3 — Metadata

Each clip's session details are looked up by talk code and turned into the
Commons file description.

The generated wikitext is shown for every clip and can be edited. What is
generated is a standard `{{Information}}` block: the session title as the
description, the speakers as the author, the conference as the source, and
the date from the schedule.

Clips without a talk code, or from a conference not on Eventyay, start from
what the CSV gave and are yours to complete.

### Converting for Commons

Commons does not accept MP4, so the MP4 cuts from screen 2 have to be
converted. This is also the screen that does it.

*Convert this clip* converts one clip, which takes a few minutes. That is the
useful one: a single session can be converted, checked and uploaded without
waiting on the rest of the day. The MP4 and the converted copy are both kept —
the MP4 for reviewing, the WebM for uploading.

Converting everything is an overnight job. Start it when you are done for the
day.

### Which format

| Format | When to choose it |
| --- | --- |
| **WebM (AV1/Opus)** | The default choice. Commons recommends it, it produces the smallest files, and it encodes faster than VP9. |
| WebM (VP9/Opus) | Larger and slower, but it is what Commons serves to viewers, so it plays immediately instead of waiting in the transcode queue. |
| Ogg Theora | Legacy. Commons advises against it for new uploads. |

On a 720p test clip, AV1 encoded about three times faster than VP9 and
produced a smaller file, so the recommended format is also the cheaper one.

---

## Step 4 — Upload

Review what is about to be sent, then upload.

Each clip shows its filename on Commons, its description and its size. Clips
already uploaded are marked with their address and are not offered again, so
re-running an interrupted batch does not create duplicates.

If you are not signed in, the screen says so. See below.

You do not have to upload from here — see
[Finishing without uploading](#finishing-without-uploading).

---

## Signing in to Commons

`File > Sign in to Commons`. No terminal needed.

### A bot password (the usual choice)

Create one at
[Special:BotPasswords](https://commons.wikimedia.org/wiki/Special:BotPasswords)
on Commons, tick the upload permissions, and paste the two values the wiki
gives you into the login window.

The secret goes into your computer's keychain — the Windows Credential
Manager, GNOME Keyring, or whatever your desktop provides — and the Pywikibot
configuration is written for you.

A bot password is revocable on its own and separate from your account
password, which is why it is the recommended route.

### A passkey or two-factor account

Use the browser tab in the login window instead.

A passkey is cryptographically bound to the browser origin
(`commons.wikimedia.org`) and cannot be typed into a desktop form — not a
limitation of this program, but the point of the design. So the wiki's own
login page is shown, you sign in there however you normally do, and the
session is picked up afterwards. That session can upload directly.

Browser sessions expire. For work spread over several days, a bot password
saves repeating this.

---

## Hardware acceleration

`File > FFmpeg settings > Hardware`.

The detection runs each encoder once rather than trusting the list FFmpeg
prints, because FFmpeg will happily list encoders the silicon does not
actually implement.

**Be clear about what this can do for you.** Commons accepts AV1, VP9 and
Theora. Hardware AV1 and VP9 encoders are still uncommon — most GPUs
accelerate H.264 and HEVC only. On such a machine the GPU speeds up the MP4
review cuts, and the conversion that actually matters for Commons stays on
the processor. The window tells you which case you are in rather than
implying a speed-up it cannot deliver.

Hardware *decoding* is offered separately and is not always a win: on the
machine this was developed on it was measurably slower than software decoding.
Try it on a single clip before turning it on for a batch.

---

## Saving your work

`File > Save project` writes the whole job to a single `.vcut` file: the
video, every clip and its state, your settings, which clips you have checked,
and the Commons address of anything already uploaded.

Reopening it picks up exactly where you left off. Cutting a conference day is
rarely one sitting, and this is what makes the second sitting painless.

Paths are stored relative to the project file, so the folder can be moved
between machines, or handed to a colleague, without breaking.

---

## Finishing without uploading

You do not have to upload from the app. After cutting, the output folder holds
everything needed to finish by hand:

```
clips/
├── mp4-cuts/            cut but not uploadable
├── commons-ready/       converted, with a .txt description beside each video
├── vcut-manifest.json   every clip's metadata and full description
├── vcut-manifest.csv    the same list as a spreadsheet
└── README.txt           what the folder holds and how to finish the upload
```

Keeping the two folders apart means that everything in `commons-ready/` is, in
fact, ready: the upload step can point at one folder and trust it.

The manifest and the `.txt` descriptions are enough to upload later — through
Commons' own upload wizard, through Pywikibot, or by reopening the project.

---

## Cutting accurately

Worth understanding, because the default is not the obvious choice.

FFmpeg can seek before it opens the file, which is instant, or after, which is
exact. Seeking before and copying streams snaps the cut to the preceding
keyframe, so a talk opens several seconds early, on the applause for the
session before. On a test file with keyframes every ten seconds, a cut asking
for 15 seconds produced 20.2.

The default does both: a fast seek to shortly before the cut, then an accurate
seek through what remains. On a twenty-minute file, cutting near the end took
0.11s against 1.06s for decoding from the start — and both landed on the exact
frame. The longer the recording, the wider that gap.

| Mode | Speed | Accuracy |
| --- | --- | --- |
| **Accurate, fast seek** *(default)* | Fast | Exact |
| Stream copy | Hundreds of times faster | Starts a few seconds early |
| Decode from the start | Slow on long files | Exact |

### When stream copy is the better choice

Copying skips encoding altogether, and the difference is not small. On one
22-minute clip from a nine-hour recording: **442 milliseconds, against 113
seconds** to re-encode. Cutting a whole day becomes a matter of seconds.

The cost is that a copied cut can only begin on a keyframe, so a clip opens
slightly early, on the tail of whatever came before. How early depends on the
recording, and the program measures yours: pick stream copy and the note under
the setting gives the real figure for your file.

On a typical conference recording with keyframes five seconds apart, clips
open about one to two seconds early, four at worst. **For conference video
that is usually fine** — there is quiet time before a talk begins, and opening
a couple of seconds early is safer than risking the speaker's first words.

So: use stream copy for review cuts of talks, where a second or two of lead-in
costs nothing and the speed is transformative. Use the accurate default when a
cut has to land on an exact frame.

---

## When something goes wrong

**"FFmpeg was not found."** FFmpeg is not on your `PATH`. Install it
([instructions](../INSTALL.md#installing-ffmpeg)), then reopen the program. You
can also point at it directly in `File > FFmpeg settings`.

**"This FFmpeg build has no AV1 encoder."** Your build lacks SVT-AV1. Choose
WebM (VP9) instead — Commons accepts it, and it is what Commons serves to
viewers anyway.

**The video will not play, but cutting works.** The player and the cutter are
different machinery: Qt plays the video, FFmpeg cuts it. Qt needs its own
backend, which on Debian or Ubuntu means
`sudo apt install libgstreamer1.0-0 gstreamer1.0-plugins-good gstreamer1.0-libav`.
Cutting is unaffected either way.

**A clip opens on the end of the previous session.** The cut snapped to a
keyframe. Check that cut accuracy is on *Accurate, fast seek* rather than
*Stream copy*.

**The session details came back empty.** Either the talk code is wrong, or the
event address is. Check the code against the schedule page — it is the short
code in the talk's URL. The schedule is cached, so a correction may need
`File > Refresh schedule`.

**Conversion is taking hours.** That is expected for AV1 on a full day. Convert
a single clip from screen 3 to get one session finished, and leave the rest for
overnight. Hardware acceleration usually will not help here — see above.

**Upload says you are not signed in, but you signed in.** A browser session
has probably expired. Sign in again, or switch to a bot password, which does
not expire.
