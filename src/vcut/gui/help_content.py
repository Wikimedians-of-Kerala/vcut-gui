"""What the help window says.

Kept apart from the window that shows it so the text can be edited without
touching any Qt code, and so the tests can check the topics line up with the
screens they claim to describe.

Bodies are a small subset of HTML — paragraphs, lists, <b> and <i> — which is
what QLabel renders. Anything richer would need a browser.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Topic:
    """One page of the help window."""

    key: str
    title: str
    body: str
    #: The screen this explains, if any: "setup", "verify", "metadata",
    #: "upload". The window opens here when help is asked for on that screen.
    screen: str = ""
    #: Words that should find this topic but do not appear in its text.
    keywords: tuple[str, ...] = field(default_factory=tuple)

    def haystack(self) -> str:
        return f"{self.title} {self.body} {' '.join(self.keywords)}".lower()


TOPICS: tuple[Topic, ...] = (
    Topic(
        key="overview",
        title="What this program does",
        keywords=("start", "begin", "introduction", "workflow", "first"),
        body="""
<p>vcut takes one long conference recording and turns it into separate
videos, one per session, ready for Wikimedia Commons.</p>

<p>The work is done in four steps, shown across the top of the window:</p>

<ol>
<li><b>Set up</b> — choose the recording, the list of timecodes, and how to
encode.</li>
<li><b>Verify and split</b> — check every cut point against the video, then
cut.</li>
<li><b>Metadata</b> — fetch each session's details and write its Commons
description.</li>
<li><b>Upload</b> — send the finished files to Commons.</li>
</ol>

<p><b>A day's recording is usually done in two sittings</b>, because
converting video for Commons is slow:</p>

<ul>
<li>First, cut everything to MP4. This takes minutes, and you can check the
cuts as you go.</li>
<li>Then convert and upload what you approved. This takes hours, so it is
work to leave running.</li>
</ul>

<p>That is why MP4 is the default. MP4 cannot be uploaded to Commons, but it
cuts almost instantly, which makes it the right format for checking. The
conversion comes later, and only for clips you kept.</p>

<p>Use <b>File &gt; Save project</b> between the two sittings and nothing is
lost.</p>
""",
    ),
    Topic(
        key="setup",
        title="Step 1 — Setting up",
        screen="setup",
        keywords=("source", "video", "csv", "folder", "event", "slug", "open"),
        body="""
<p>Four things to fill in.</p>

<p><b>The source video.</b> Your recording. It is examined as soon as you
choose it, and its length, resolution, codecs and frame rate appear beneath.
If something looks wrong here — a length of zero, no video stream — the file
is the problem, and it is better to know now than after cutting.</p>

<p>The output folder is filled in for you. Change it if you want the clips
somewhere else.</p>

<p><b>The timecodes.</b> A CSV or TSV saying where each session starts and
ends. See <i>The timecode list</i> in this window for the format.</p>

<p><b>The conference schedule.</b> Where session details are fetched from.
You can give it as a short slug or a full address — <i>india26</i>,
<i>wikicon/india26</i>, or the whole schedule URL all work. Leave it empty if
the conference is not on Eventyay; you will type the details yourself at step
3.</p>

<p>The schedule is fetched once and kept, then searched locally. That is
faster than asking the server for each clip, and kinder to it.</p>

<p><b>How to encode.</b> Two settings matter:</p>

<ul>
<li><b>Cut accuracy</b> — leave this on <i>Accurate, fast seek</i>. See
<i>Why the cuts land where they do</i>.</li>
<li><b>Output format</b> — leave this on MP4 for the first pass.</li>
</ul>

<p>Everything else is in <b>File &gt; FFmpeg settings</b>, including hardware
acceleration and converting mono audio to stereo.</p>
""",
    ),
    Topic(
        key="verify",
        title="Step 2 — Verifying and splitting",
        screen="verify",
        keywords=("timeline", "player", "zoom", "preview", "trim", "cut", "split"),
        body="""
<p>This is where the real work happens: confirming every cut point before
committing to an encode that may run for hours.</p>

<p>The player sits beside the clip list, with the timeline across the full
width beneath them both. Every clip is drawn on that timeline in
<b>dark blue</b>, and the one you have selected in <b>orange</b>. The shape of
the day is visible at a glance — and so is any gap where a session was
missed.</p>

<p><b>Checking a cut.</b> Click a row and the player seeks to that clip's
start. <i>Preview</i> plays the opening seconds, which is usually enough to
tell whether you caught the speaker's first words or the tail of the session
before.</p>

<p>Step through with the keyboard: <b>J</b> and <b>L</b> move a second,
<b>Shift</b> with the arrow keys moves ten, and <b>,</b> and <b>.</b> move a
single frame.</p>

<p>When a cut is right, press <b>V</b>. It marks the clip checked and moves
to the next. Working down the list with V is the quickest way through a
day.</p>

<p><b>Fixing a cut</b>, in increasing order of precision:</p>

<ul>
<li><b>Type it</b> into the table.</li>
<li><b>Take it from the playhead</b> — park the playhead where the cut
belongs and press <b>I</b> for the start or <b>O</b> for the end.</li>
<li><b>Zoom in first.</b> On a nine-hour recording a clip is a few pixels
wide. The magnifier buttons, or Ctrl with the mouse wheel, narrow the view
around the playhead. <i>Zoom to clip</i> fills the timeline with one session,
which is what you want for trimming to the frame.</li>
</ul>

<p><b>Clips the list missed.</b> <i>Add clip</i> makes a new row,
<i>Duplicate</i> copies the selected one, <i>Remove</i> deletes it. A session
nobody wrote down is no obstacle: find it in the video, add a clip, and set
both ends from the playhead.</p>

<p><b>Rows that cannot work</b> — an end before its start, or a time past the
end of the recording — are flagged before any encoding starts. The split will
not begin while any remain.</p>

<p><b>Splitting.</b> <i>Split the video</i> shows what it is about to do and
asks you to confirm, then reports progress per clip. Cancelling finishes the
clip it is on rather than leaving a half-written file.</p>
""",
    ),
    Topic(
        key="metadata",
        title="Step 3 — Metadata and converting",
        screen="metadata",
        keywords=("wikitext", "description", "template", "information",
                  "convert", "webm", "av1", "vp9", "format"),
        body="""
<p>Each clip's session details are looked up by talk code and turned into its
Commons file description.</p>

<p>What is generated is a standard <i>Information</i> block: the session title
as the description, the speakers as the author, the conference as the source,
and the date from the schedule. Every clip's wikitext is shown and can be
edited before anything is uploaded.</p>

<p>Clips without a talk code, or from a conference not on Eventyay, start
from whatever the timecode list gave and are yours to complete.</p>

<p><b>Converting for Commons.</b> Commons does not accept MP4, so the cuts
from step 2 have to be converted. This screen does that too.</p>

<p><i>Convert this clip</i> converts one clip, taking a few minutes. That is
the useful one: a single session can be converted, checked and uploaded
without waiting for the rest of the day. Both files are kept — the MP4 for
reviewing, the WebM for uploading.</p>

<p>Converting everything is an overnight job. Start it when you are done for
the day.</p>

<p><b>Which format:</b></p>

<ul>
<li><b>WebM (AV1/Opus)</b> — the default. Commons recommends it, it makes the
smallest files, and it encodes faster than VP9.</li>
<li><b>WebM (VP9/Opus)</b> — larger and slower, but it is what Commons serves
to viewers, so it plays immediately instead of waiting in the transcode
queue.</li>
<li><b>Ogg Theora</b> — legacy. Commons advises against it for new
uploads.</li>
</ul>

<p>On a 720p test clip, AV1 encoded about three times faster than VP9 and
produced a smaller file, so the recommended format is also the cheaper
one.</p>
""",
    ),
    Topic(
        key="upload",
        title="Step 4 — Uploading",
        screen="upload",
        keywords=("commons", "send", "publish", "duplicate", "pywikibot"),
        body="""
<p>Review what is about to be sent, then upload.</p>

<p>Each clip shows the name it will have on Commons, its description and its
size. Clips already uploaded are marked with their address and are not
offered again, so re-running an interrupted batch will not create
duplicates.</p>

<p>If you are not signed in, the screen says so. See <i>Signing in to
Commons</i> in this window.</p>

<p><b>You do not have to upload from here.</b> See <i>Finishing without
uploading</i>.</p>
""",
    ),
    Topic(
        key="csv",
        title="The timecode list",
        keywords=("csv", "tsv", "columns", "format", "spreadsheet", "code", "id"),
        body="""
<p>A CSV or TSV saying where each session sits within the recording. Tab- or
comma-separated, with a header row:</p>

<p><tt>programme&nbsp;&nbsp;start_time&nbsp;&nbsp;end_time&nbsp;&nbsp;eventyay_id&nbsp;&nbsp;author</tt><br>
<tt>Welcome&nbsp;and&nbsp;Opening&nbsp;&nbsp;00:10:59&nbsp;&nbsp;00:33:34&nbsp;&nbsp;7NXGTK&nbsp;&nbsp;Asha&nbsp;Menon</tt></p>

<p>Only the start and end times are required. Column names are matched
loosely — <i>title</i>, <i>session</i> and <i>programme</i> all work, as do
<i>start</i> and <i>start_time</i>. Columns that are not recognised are
carried through untouched, so you can keep a <i>room</i> or <i>notes</i>
column of your own.</p>

<p><b>Times are positions within the recording</b>, written HH:MM:SS — not
clock times. If your schedule is in clock times, subtract the moment
recording began.</p>

<p>The <i>eventyay_id</i> is the talk code from the schedule — the short code
in a talk's address. It is what links a clip to its session details. Rows
without one still work, falling back to whatever the list says.</p>

<p>Getting a few rows right matters more than getting every row in. Sessions
the list missed can be added at step 2, where you can see the video.</p>

<p>Two working examples ship with the program, in the <i>examples</i>
folder.</p>
""",
    ),
    Topic(
        key="login",
        title="Signing in to Commons",
        keywords=("password", "bot", "passkey", "2fa", "two-factor",
                  "account", "keychain", "credentials", "log in"),
        body="""
<p><b>File &gt; Sign in to Commons.</b> No terminal needed.</p>

<p><b>A bot password</b> is the usual choice. Create one at
<i>Special:BotPasswords</i> on Commons, tick the upload permissions, and
paste the two values into the login window.</p>

<p>The secret goes into your computer's keychain — the Windows Credential
Manager, GNOME Keyring, or whatever your desktop provides — and the Pywikibot
configuration is written for you. A bot password can be revoked on its own
and is separate from your account password, which is why it is
recommended.</p>

<p><b>A passkey or two-factor account</b> needs the browser tab instead.</p>

<p>A passkey is cryptographically tied to the browser address
(<i>commons.wikimedia.org</i>) and cannot be typed into a desktop form. That
is the point of the design, not a limitation here. So the wiki's own login
page is shown, you sign in there however you normally do, and the session is
picked up afterwards. That session can upload directly.</p>

<p>Browser sessions expire. For work spread over several days, a bot password
saves repeating this.</p>

<p>Some downloadable builds leave the embedded browser out, because it is
very large. Those builds say so in the login window; use a bot password
instead.</p>
""",
    ),
    Topic(
        key="accuracy",
        title="Why the cuts land where they do",
        keywords=("keyframe", "seek", "accurate", "stream copy", "drift",
                  "early", "accuracy"),
        body="""
<p>Worth a minute, because the default is not the obvious choice.</p>

<p>FFmpeg can seek before it opens the file, which is instant, or after,
which is exact. Seeking before and copying the streams snaps the cut to the
nearest earlier keyframe — so a talk opens several seconds early, on the
applause for the session before. On a test file with keyframes every ten
seconds, a cut asking for 15 seconds produced 20.2.</p>

<p>The default does both: a fast seek to shortly before the cut, then an
accurate seek through what remains. On a twenty-minute file, cutting near the
end took 0.11 seconds against 1.06 for decoding from the start — and both
landed on the exact frame. The longer the recording, the wider that gap.</p>

<ul>
<li><b>Accurate, fast seek</b> (the default) — fast, and exact.</li>
<li><b>Stream copy</b> — instant, but snaps to keyframes.</li>
<li><b>Decode from the start</b> — exact, but slow on long files.</li>
</ul>

<p>Choose stream copy only when the cut points happen to be keyframes and you
need the speed.</p>

<p>If a clip opens on the end of the previous session, this is why: check
that cut accuracy is not set to stream copy.</p>
""",
    ),
    Topic(
        key="hardware",
        title="Hardware acceleration",
        keywords=("gpu", "nvenc", "vaapi", "qsv", "amf", "graphics", "faster",
                  "speed"),
        body="""
<p><b>File &gt; FFmpeg settings &gt; Hardware.</b></p>

<p>Detection runs each encoder once rather than trusting the list FFmpeg
prints, because FFmpeg will happily list encoders the hardware does not
actually implement.</p>

<p><b>Be clear about what this can do for you.</b> Commons accepts AV1, VP9
and Theora. Hardware AV1 and VP9 encoders are still uncommon — most graphics
chips accelerate H.264 and HEVC only. On such a machine the GPU speeds up the
MP4 cuts you make for reviewing, while the conversion that actually matters
for Commons stays on the processor. The window tells you which case you are
in rather than implying a speed-up it cannot deliver.</p>

<p>Hardware <i>decoding</i> is offered separately and is not always a win: on
the machine this was developed on it was measurably slower than decoding in
software. Try it on one clip before turning it on for a batch.</p>
""",
    ),
    Topic(
        key="projects",
        title="Saving your work",
        keywords=("project", "vcut", "save", "resume", "reopen", "session"),
        body="""
<p><b>File &gt; Save project</b> writes the whole job to a single
<i>.vcut</i> file: the video, every clip and its state, your settings, which
clips you have checked, and the Commons address of anything already
uploaded.</p>

<p>Reopening it picks up exactly where you left off. Cutting a conference day
is rarely one sitting, and this is what makes the second one painless.</p>

<p>Paths are stored relative to the project file, so the folder can be moved
between machines, or handed to a colleague, without breaking.</p>
""",
    ),
    Topic(
        key="offline",
        title="Finishing without uploading",
        keywords=("manifest", "folder", "sidecar", "later", "by hand",
                  "output", "where"),
        body="""
<p>You do not have to upload from the program. After cutting, the output
folder holds everything needed to finish by hand:</p>

<ul>
<li><b>mp4-cuts/</b> — cut, but not uploadable.</li>
<li><b>commons-ready/</b> — converted, with a description beside each
video.</li>
<li><b>vcut-manifest.json</b> — every clip's metadata and full
description.</li>
<li><b>vcut-manifest.csv</b> — the same list as a spreadsheet.</li>
<li><b>README.txt</b> — what the folder holds and how to finish.</li>
</ul>

<p>Keeping the two folders apart means everything in <i>commons-ready</i> is,
in fact, ready: the upload step can point at one folder and trust it.</p>

<p>The manifest and the descriptions beside each file are enough to upload
later — through Commons' own upload wizard, through Pywikibot, or by
reopening the project here.</p>
""",
    ),
    Topic(
        key="trouble",
        title="When something goes wrong",
        keywords=("error", "problem", "fail", "broken", "help", "ffmpeg",
                  "missing", "not found", "troubleshooting"),
        body="""
<p><b>"FFmpeg was not found."</b> FFmpeg is not installed, or not where the
program can find it. Install it, then reopen the program; you can also point
straight at it in <b>File &gt; FFmpeg settings</b>.</p>

<p><b>"This FFmpeg build has no AV1 encoder."</b> Your copy of FFmpeg was
built without SVT-AV1. Choose WebM (VP9) instead — Commons accepts it, and it
is what Commons serves to viewers anyway.</p>

<p><b>The video will not play, but cutting works.</b> These are different
machinery: Qt plays the video, FFmpeg cuts it. Qt needs its own backend,
which on Debian or Ubuntu means installing the GStreamer plugins. Cutting is
unaffected either way.</p>

<p><b>A clip opens on the end of the previous session.</b> The cut snapped to
a keyframe. See <i>Why the cuts land where they do</i>.</p>

<p><b>The session details came back empty.</b> Either the talk code is wrong
or the event address is. Check the code against the schedule page — it is the
short code in the talk's address.</p>

<p><b>Conversion is taking hours.</b> Expected, for AV1 on a full day.
Convert a single clip from step 3 to get one session finished, and leave the
rest for overnight. Hardware acceleration usually will not help; see
<i>Hardware acceleration</i>.</p>

<p><b>Upload says you are not signed in, but you signed in.</b> A browser
session has probably expired. Sign in again, or switch to a bot password,
which does not.</p>
""",
    ),
)


def by_key(key: str) -> Topic | None:
    for topic in TOPICS:
        if topic.key == key:
            return topic
    return None


def for_screen(screen: str) -> Topic | None:
    """The topic explaining a screen, if one does."""
    for topic in TOPICS:
        if topic.screen and topic.screen == screen:
            return topic
    return None
