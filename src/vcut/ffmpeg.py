"""Building and running ffmpeg commands.

Cut accuracy is the subtle part. Placing ``-ss`` *after* ``-i`` is frame-accurate
but decodes everything up to the cut point, which is slow on a nine-hour
recording. Placing it *before* ``-i`` seeks fast but, with ``-c copy``, snaps the
cut to the preceding keyframe — so a talk can open several seconds early, on the
tail of the previous session.

:class:`CutMode` exposes the trade-off:

``COPY``
    Fast seek plus stream copy. Instant, but keyframe-snapped.
``SMART``
    Fast seek to shortly before the cut, then an accurate seek for the
    remainder, re-encoding. Frame-accurate without decoding the whole file.
``REENCODE``
    Accurate seek from the start of the file. Slowest, most predictable.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from collections import deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .models import Clip


class CutMode(str, Enum):
    COPY = "copy"
    SMART = "smart"
    REENCODE = "reencode"


#: How far before the cut point SMART mode seeks with the fast seeker. It must
#: comfortably exceed one keyframe interval so the accurate seek has material to
#: work with, while staying short enough that decoding it is cheap.
SMART_PREROLL_SECONDS = 20.0


class AudioLayout(str, Enum):
    """What to do with the source's audio channels.

    Conference recordings often arrive mono, from a single mic feed. Players
    then put the sound in one ear, or in one speaker, which sounds broken
    even though the file is fine.
    """

    KEEP = "keep"
    STEREO = "stereo"        # duplicate mono to both channels
    FORCE_MONO = "mono"      # downmix to one channel

    @property
    def label(self) -> str:
        return {
            AudioLayout.KEEP: "Keep the source layout",
            AudioLayout.STEREO: "Make mono sound stereo (duplicate to both)",
            AudioLayout.FORCE_MONO: "Downmix everything to mono",
        }[self]


class OutputFormat(str, Enum):
    """Container/codec target for the produced clips.

    Wikimedia Commons does not accept MP4; uploads must be WebM, Ogg Theora or
    MPEG. Commons recommends WebM with AV1 video and Opus audio, so that is the
    default upload target. MP4 remains the fast local format for reviewing cuts
    before anything is converted.

    See https://commons.wikimedia.org/wiki/Commons:File_types#Video
    """

    MP4 = "mp4"
    WEBM_AV1 = "webm-av1"
    WEBM_VP9 = "webm-vp9"
    OGV = "ogv"

    @property
    def extension(self) -> str:
        return "webm" if self.value.startswith("webm") else self.value

    @property
    def commons_compatible(self) -> bool:
        return self is not OutputFormat.MP4

    @property
    def label(self) -> str:
        return {
            OutputFormat.MP4: "MP4 (H.264/AAC) — local review only, not uploadable",
            OutputFormat.WEBM_AV1: "WebM (AV1/Opus) — recommended for Commons",
            OutputFormat.WEBM_VP9: "WebM (VP9/Opus) — plays before transcoding finishes",
            OutputFormat.OGV: "Ogg Theora — legacy, avoid for new uploads",
        }[self]

    @property
    def hint(self) -> str:
        """Longer explanation shown beside the format chooser."""
        return {
            OutputFormat.MP4: (
                "Fastest to produce and fine for checking cuts locally, but "
                "Wikimedia Commons rejects MP4. Convert before uploading."
            ),
            OutputFormat.WEBM_AV1: (
                "What Commons recommends: the smallest upload and the fastest "
                "encode here. Commons then builds its own VP9 versions for "
                "playback, which can take a while in its job queue."
            ),
            OutputFormat.WEBM_VP9: (
                "Larger and slower to encode than AV1, but it is the format "
                "Commons serves to viewers, so the file is watchable straight "
                "away rather than waiting on the transcode queue."
            ),
            OutputFormat.OGV: (
                "Supported for backwards compatibility only. Commons advises "
                "against converting to Theora for new uploads."
            ),
        }[self]


#: Codec defaults per target.
#:
#: SVT-AV1 is the AV1 encoder worth using: measured on a 720p clip it ran ~3x
#: faster than VP9 and produced a smaller file, where libaom was several times
#: slower. ``preset`` trades speed for compression (0 slowest, 13 fastest).
FORMAT_DEFAULTS: dict[OutputFormat, dict[str, object]] = {
    OutputFormat.MP4: {
        "video_codec": "libx264", "audio_codec": "aac",
        "crf": 20, "audio_bitrate": "192k",
    },
    OutputFormat.WEBM_AV1: {
        "video_codec": "libsvtav1", "audio_codec": "libopus",
        "crf": 35, "audio_bitrate": "128k",
    },
    OutputFormat.WEBM_VP9: {
        "video_codec": "libvpx-vp9", "audio_codec": "libopus",
        "crf": 31, "audio_bitrate": "128k",
    },
    OutputFormat.OGV: {
        "video_codec": "libtheora", "audio_codec": "libvorbis",
        "crf": 7, "audio_bitrate": "192k",
    },
}

#: Fallback order when the preferred AV1 encoder is not compiled in.
AV1_ENCODERS = ("libsvtav1", "libaom-av1", "librav1e")


def available_encoders(ffmpeg_path: str = "") -> set[str]:
    """Names of the encoders this ffmpeg build supports."""
    try:
        exe = find_executable("ffmpeg", ffmpeg_path)
    except FFmpegError:
        return set()
    try:
        result = subprocess.run(
            [exe, "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return set()
    names = set()
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and len(parts[0]) == 6:
            names.add(parts[1])
    return names


def resolve_av1_encoder(ffmpeg_path: str = "") -> str | None:
    """Pick the best available AV1 encoder, or ``None`` if there is none."""
    encoders = available_encoders(ffmpeg_path)
    for candidate in AV1_ENCODERS:
        if candidate in encoders:
            return candidate
    return None


class FFmpegError(RuntimeError):
    """Raised when ffmpeg is missing, or exits non-zero."""


@dataclass
class EncodingSettings:
    """Everything the user can tune about how clips are produced."""

    cut_mode: CutMode = CutMode.SMART
    output_format: OutputFormat = OutputFormat.MP4
    video_codec: str = "libx264"
    crf: int = 20
    preset: str = "medium"
    audio_codec: str = "aac"
    audio_bitrate: str = "192k"
    audio_layout: AudioLayout = AudioLayout.KEEP
    scale: str = ""          # e.g. "1280:-2"; empty means keep source size
    fps: str = ""            # e.g. "30"; empty means keep source rate
    threads: int = 0         # 0 lets ffmpeg decide
    # VP9 only: 0 is slowest/best, 5 is fastest. 4 is roughly realtime.
    vp9_cpu_used: int = 4
    vp9_two_pass: bool = False
    # SVT-AV1 only: 0 is slowest/best quality, 13 is fastest. 8 is a good balance.
    av1_preset: int = 8
    #: Use a GPU encoder when one exists for the chosen codec. Falls back to
    #: the CPU silently when it does not — most GPUs cannot encode AV1 or VP9.
    use_hardware: bool = False
    #: Chosen hardware encoder, e.g. "h264_vaapi"; empty means pick the best.
    hardware_encoder: str = ""
    hardware_device: str = ""
    #: Quality for hardware encoders, which use a quantiser rather than CRF.
    hardware_quality: int = 23
    pad_start: float = 0.0   # seconds of lead-in added to every clip
    pad_end: float = 0.0     # seconds of lead-out added to every clip
    extra_args: list[str] = field(default_factory=list)
    overwrite: bool = False

    def to_dict(self) -> dict:
        data = {k: v for k, v in self.__dict__.items()}
        data["cut_mode"] = self.cut_mode.value
        data["output_format"] = self.output_format.value
        data["audio_layout"] = self.audio_layout.value
        return data

    @classmethod
    def from_dict(cls, data: dict) -> EncodingSettings:
        known = {k: v for k, v in (data or {}).items() if k in cls.__dataclass_fields__}
        if "cut_mode" in known:
            known["cut_mode"] = CutMode(known["cut_mode"])
        if "output_format" in known:
            known["output_format"] = OutputFormat(known["output_format"])
        if "audio_layout" in known:
            try:
                known["audio_layout"] = AudioLayout(known["audio_layout"])
            except ValueError:
                known["audio_layout"] = AudioLayout.KEEP
        return cls(**known)

    @property
    def container(self) -> str:
        return self.output_format.extension

    def with_format(self, fmt: OutputFormat) -> EncodingSettings:
        """Copy these settings retargeted at another container.

        Codecs that belong to the old container are swapped for the new one's
        defaults; anything the user set that still applies is kept.
        """
        import copy

        clone = copy.deepcopy(self)
        clone.output_format = fmt
        defaults = FORMAT_DEFAULTS[fmt]
        clone.video_codec = str(defaults["video_codec"])
        clone.audio_codec = str(defaults["audio_codec"])
        clone.crf = int(defaults["crf"])
        clone.audio_bitrate = str(defaults["audio_bitrate"])
        # Stream copy cannot change container codecs; force a re-encode.
        if fmt is not OutputFormat.MP4 and clone.cut_mode is CutMode.COPY:
            clone.cut_mode = CutMode.SMART
        return clone


@dataclass
class MediaInfo:
    """What ``ffprobe`` tells us about the source file."""

    duration: float = 0.0
    width: int = 0
    height: int = 0
    video_codec: str = ""
    audio_codec: str = ""
    fps: float = 0.0
    size_bytes: int = 0
    #: Seconds between keyframes, 0.0 if not measured. This is what decides
    #: how far a stream-copied cut drifts from the time asked for.
    keyframe_interval: float = 0.0
    #: The full ffprobe payload, for the detailed information window.
    raw: dict = field(default_factory=dict)

    @property
    def resolution(self) -> str:
        return f"{self.width}×{self.height}" if self.width and self.height else "unknown"

    @property
    def format_name(self) -> str:
        return str(self.raw.get("format", {}).get("format_long_name", ""))

    @property
    def bitrate(self) -> int:
        try:
            return int(self.raw.get("format", {}).get("bit_rate") or 0)
        except (TypeError, ValueError):
            return 0

    def streams(self, kind: str = "") -> list[dict]:
        """The probed streams, optionally of one type."""
        found = self.raw.get("streams", []) or []
        if kind:
            return [s for s in found if s.get("codec_type") == kind]
        return list(found)


def find_executable(name: str, configured: str = "") -> str:
    """Locate ffmpeg/ffprobe, preferring an explicitly configured path."""
    if configured:
        candidate = Path(configured)
        if candidate.is_file():
            return str(candidate)
        resolved = shutil.which(configured)
        if resolved:
            return resolved
    resolved = shutil.which(name)
    if resolved:
        return resolved
    raise FFmpegError(
        f"{name} was not found. Install FFmpeg and make sure it is on your PATH, "
        f"or set its location in Settings."
    )


def probe(source: str | Path, ffprobe_path: str = "") -> MediaInfo:
    """Inspect a media file with ffprobe."""
    exe = find_executable("ffprobe", ffprobe_path)
    command = [
        exe, "-v", "error",
        "-print_format", "json",
        "-show_format", "-show_streams",
        str(source),
    ]
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=120, check=False
        )
    except subprocess.TimeoutExpired as exc:
        raise FFmpegError(f"ffprobe timed out inspecting {source}") from exc

    if completed.returncode != 0:
        raise FFmpegError(f"ffprobe failed: {completed.stderr.strip()[:400]}")

    payload = json.loads(completed.stdout or "{}")
    info = MediaInfo(raw=payload)

    fmt = payload.get("format", {})
    info.duration = float(fmt.get("duration") or 0.0)
    info.size_bytes = int(fmt.get("size") or 0)

    for stream in payload.get("streams", []):
        kind = stream.get("codec_type")
        if kind == "video" and not info.video_codec:
            info.video_codec = stream.get("codec_name", "")
            info.width = int(stream.get("width") or 0)
            info.height = int(stream.get("height") or 0)
            info.fps = _parse_fraction(stream.get("avg_frame_rate", "0/0"))
            if not info.duration:
                info.duration = float(stream.get("duration") or 0.0)
        elif kind == "audio" and not info.audio_codec:
            info.audio_codec = stream.get("codec_name", "")

    return info


def _parse_fraction(value: str) -> float:
    try:
        numerator, _, denominator = str(value).partition("/")
        den = float(denominator or 1)
        return float(numerator) / den if den else 0.0
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0


def build_command(
    source: str | Path,
    output: str | Path,
    start: float,
    end: float,
    settings: EncodingSettings,
    *,
    ffmpeg_path: str = "",
) -> list[str]:
    """Assemble the ffmpeg argument list for one clip."""
    if end <= start:
        raise ValueError("end time must be after start time")

    exe = find_executable("ffmpeg", ffmpeg_path)
    start = max(0.0, start - settings.pad_start)
    end = end + settings.pad_end
    duration = end - start

    command = [exe, "-hide_banner", "-nostdin"]
    command.append("-y" if settings.overwrite else "-n")
    # Device selection has to precede -i, so it goes on before the seek.
    command += _hardware_input_args(settings)

    cut_mode = settings.cut_mode
    if cut_mode is CutMode.COPY and settings.output_format is not OutputFormat.MP4:
        # Copying streams cannot change codecs, so a WebM/Ogg target must encode.
        cut_mode = CutMode.SMART

    if cut_mode is CutMode.COPY:
        # Fast seek, then copy: quickest, snapped to the preceding keyframe.
        command += ["-ss", f"{start:.3f}", "-i", str(source), "-t", f"{duration:.3f}"]
        command += ["-c", "copy", "-avoid_negative_ts", "make_zero"]

    elif cut_mode is CutMode.SMART:
        # Seek fast to just before the cut, then seek accurately the rest of the
        # way. Decoding is limited to the pre-roll, so this stays quick.
        preroll = min(SMART_PREROLL_SECONDS, start)
        command += ["-ss", f"{start - preroll:.3f}", "-i", str(source)]
        if preroll:
            command += ["-ss", f"{preroll:.3f}"]
        command += ["-t", f"{duration:.3f}"]
        command += _encode_args(settings)

    else:  # REENCODE — accurate seek from the beginning of the input.
        command += ["-i", str(source), "-ss", f"{start:.3f}", "-t", f"{duration:.3f}"]
        command += _encode_args(settings)

    if settings.threads:
        command += ["-threads", str(settings.threads)]

    command += list(settings.extra_args)
    command += ["-progress", "pipe:1", "-nostats"]
    command.append(str(output))
    return command


def audio_filter(settings: EncodingSettings, *, source_channels: int = 0) -> str:
    """The ``-af`` value for the chosen channel layout, or an empty string.

    ``source_channels`` lets the stereo option leave genuinely stereo audio
    alone; without it the filter is applied regardless, which is harmless
    but wasteful.
    """
    if settings.audio_layout is AudioLayout.STEREO:
        if source_channels and source_channels >= 2:
            return ""
        # Copy the single channel to both, rather than relying on ffmpeg's
        # default upmix, so the result is centred rather than one-sided.
        return "pan=stereo|c0=c0|c1=c0"
    if settings.audio_layout is AudioLayout.FORCE_MONO:
        return "pan=mono|c0=0.5*c0+0.5*c1"
    return ""


def _audio_args(settings: EncodingSettings, source_channels: int = 0) -> list[str]:
    """Audio codec flags, including any channel-layout filter."""
    args: list[str] = []
    filter_text = audio_filter(settings, source_channels=source_channels)
    if filter_text:
        args += ["-af", filter_text]
    args += ["-c:a", settings.audio_codec]
    if settings.audio_codec not in ("copy",):
        args += ["-b:a", settings.audio_bitrate]
    return args


def _hardware_input_args(settings: EncodingSettings) -> list[str]:
    """Flags that must precede ``-i`` when encoding on the GPU."""
    encoder = _hardware_encoder(settings)
    if encoder and encoder.endswith("_vaapi"):
        device = settings.hardware_device or _default_render_node()
        if device:
            return ["-vaapi_device", device]
    return []


def _default_render_node() -> str:
    import os
    import sys

    if sys.platform != "linux":
        return ""
    for node in ("/dev/dri/renderD128", "/dev/dri/renderD129"):
        if os.path.exists(node):
            return node
    return ""


def _hardware_encoder(settings: EncodingSettings) -> str:
    """The GPU encoder to use, or empty when encoding on the CPU."""
    if not settings.use_hardware or settings.video_codec == "copy":
        return ""
    return settings.hardware_encoder


def _encode_args(settings: EncodingSettings) -> list[str]:
    """Video/audio encoder flags for the configured container."""
    hardware = _hardware_encoder(settings)
    if hardware:
        return _hardware_encode_args(settings, hardware)

    args = ["-c:v", settings.video_codec]

    if settings.video_codec not in ("copy",):
        args += ["-crf", str(settings.crf)]
        if settings.video_codec == "libsvtav1":
            # SVT-AV1 tunes speed with -preset and benefits from explicit
            # threading on many-core machines.
            args += ["-preset", str(settings.av1_preset), "-pix_fmt", "yuv420p"]
        elif settings.video_codec in ("libaom-av1", "librav1e"):
            args += ["-b:v", "0", "-cpu-used", str(settings.vp9_cpu_used), "-row-mt", "1"]
        elif settings.video_codec.startswith("libvpx"):
            # VP9 needs an explicit zero bitrate to run in constant-quality mode.
            args += ["-b:v", "0", "-deadline", "good",
                     "-cpu-used", str(settings.vp9_cpu_used), "-row-mt", "1"]
        elif settings.video_codec == "libtheora":
            args += ["-q:v", str(settings.crf)]
        else:
            args += ["-preset", settings.preset]

    filters = []
    if settings.scale:
        filters.append(f"scale={settings.scale}")
    if settings.fps:
        filters.append(f"fps={settings.fps}")
    if filters:
        args += ["-vf", ",".join(filters)]

    args += _audio_args(settings)

    # Keep the moov atom at the front so MP4 clips scrub without a full download.
    if settings.output_format is OutputFormat.MP4:
        args += ["-movflags", "+faststart"]
    return args


def _hardware_encode_args(settings: EncodingSettings, encoder: str) -> list[str]:
    """Encoder flags for a GPU encoder.

    Hardware encoders take a quantiser rather than a CRF, and VAAPI needs
    the frames uploaded to the GPU first.
    """
    args: list[str] = []
    filters = []
    if encoder.endswith("_vaapi"):
        # Everything must be in a format the GPU accepts before upload.
        filters.append("format=nv12")
    if settings.scale:
        filters.append(f"scale={settings.scale}")
    if settings.fps:
        filters.append(f"fps={settings.fps}")
    if encoder.endswith("_vaapi"):
        filters.append("hwupload")
    if filters:
        args += ["-vf", ",".join(filters)]

    args += ["-c:v", encoder]
    quality = str(settings.hardware_quality)
    if encoder.endswith("_vaapi"):
        args += ["-qp", quality]
    elif encoder.endswith("_nvenc"):
        args += ["-rc", "constqp", "-qp", quality, "-preset", "p4"]
    elif encoder.endswith("_qsv"):
        args += ["-global_quality", quality]
    elif encoder.endswith("_amf"):
        args += ["-rc", "cqp", "-qp_i", quality, "-qp_p", quality]
    elif encoder.endswith("_videotoolbox"):
        args += ["-q:v", quality]

    args += _audio_args(settings)
    if settings.output_format is OutputFormat.MP4:
        args += ["-movflags", "+faststart"]
    return args


_PROGRESS_KEY_RE = re.compile(r"^(\w+)=(.*)$")


def _describe_signal(number: int) -> str:
    """Explain a signal that killed ffmpeg.

    A bare "exited with code -11" tells the user nothing they can act on,
    and the two that actually happen here have very different causes.
    """
    try:
        name = signal.Signals(number).name
    except ValueError:
        return f"ffmpeg was killed by signal {number}."

    hints = {
        "SIGKILL": (
            "ffmpeg was killed by the system (SIGKILL), which usually means "
            "it ran out of memory. Try one clip at a time, or a faster "
            "preset."
        ),
        "SIGSEGV": (
            "ffmpeg crashed (SIGSEGV). This is a fault in ffmpeg or one of "
            "its encoders, not in the file. Try a different encoder or "
            "preset, or update ffmpeg."
        ),
        "SIGTERM": "ffmpeg was stopped (SIGTERM).",
        "SIGINT": "ffmpeg was interrupted (SIGINT).",
    }
    return hints.get(name, f"ffmpeg was killed by {name} (signal {number}).")


def run_command(
    command: list[str],
    duration: float,
    *,
    on_progress: Callable[[float], None] | None = None,
    on_log: Callable[[str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> int:
    """Run ffmpeg, reporting progress as a 0..1 fraction.

    Returns the exit code. Raises :class:`FFmpegError` if the process cannot be
    started. Cancellation terminates the child and returns its exit code.
    """
    # Progress goes to a file, not a pipe.
    #
    # "-progress pipe:1" only works while something keeps reading that pipe.
    # A file has no buffer to fill, cannot wedge ffmpeg if we stop reading,
    # and still holds the last report if the process dies -- so a crash can
    # be described by how far it got.
    progress_file: Path | None = None
    if any(part == "pipe:1" for part in command):
        handle, name = tempfile.mkstemp(prefix="vcut-progress-", suffix=".txt")
        os.close(handle)
        progress_file = Path(name)
        command = [str(progress_file) if part == "pipe:1" else part
                   for part in command]

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            **_no_window_kwargs(),
        )
    except OSError as exc:
        if progress_file:
            progress_file.unlink(missing_ok=True)
        raise FFmpegError(f"could not start ffmpeg: {exc}") from exc

    assert process.stderr is not None

    # stderr still has to be drained while ffmpeg runs, not after it exits.
    #
    # ffmpeg writes steadily to stderr, and a pipe holds only about 64 KB.
    # Letting it fill blocks ffmpeg on its next write: progress stops and the
    # encode appears to freeze part-way through with the processor idle. On a
    # long clip that happens every time.
    #
    # The tail is capped because a failing ffmpeg can emit a warning per
    # frame, and the last lines are the ones that say what went wrong.
    stderr_tail: deque[str] = deque(maxlen=200)

    def drain_stderr() -> None:
        for raw in process.stderr:  # type: ignore[union-attr]
            text = raw.rstrip()
            if text:
                stderr_tail.append(text)

    reader = threading.Thread(target=drain_stderr, daemon=True)
    reader.start()

    try:
        _follow_progress(
            process, progress_file, duration,
            on_progress=on_progress, should_cancel=should_cancel,
        )
        process.wait()
    finally:
        reader.join(timeout=5)
        if progress_file:
            progress_file.unlink(missing_ok=True)

    if on_log:
        for text in stderr_tail:
            on_log(text)

    # A negative code is a signal, which otherwise reaches the user as the
    # bare and unhelpful "ffmpeg exited with code -11".
    code = process.returncode
    if code is not None and code < 0 and on_log:
        on_log(_describe_signal(-code))

    # A killed ffmpeg leaves the output it had opened but never wrote. That
    # empty file then blocks every retry, because the commands carry "-n" to
    # avoid clobbering real work -- so the next attempt fails with "already
    # exists" and the user is stuck until they clear the folder by hand.
    if code != 0:
        _remove_empty_output(command, on_log)
    return code


def _remove_empty_output(
    command: list[str],
    on_log: Callable[[str], None] | None = None,
) -> None:
    """Delete the output file if the run left it empty."""
    if not command:
        return
    target = Path(command[-1])
    try:
        if target.is_file() and target.stat().st_size == 0:
            target.unlink()
            if on_log:
                on_log(f"Removed the empty {target.name} left by the failure.")
    except OSError:
        pass


def _follow_progress(
    process: subprocess.Popen,
    progress_file: Path | None,
    duration: float,
    *,
    on_progress: Callable[[float], None] | None,
    should_cancel: Callable[[], bool] | None,
) -> None:
    """Watch ffmpeg until it finishes, reporting how far it has got."""
    offset = 0
    while process.poll() is None:
        if should_cancel and should_cancel():
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            return

        if progress_file and on_progress and duration > 0:
            offset = _read_progress(progress_file, offset, duration, on_progress)
        time.sleep(0.2)

    # One last read: the final lines are usually written as ffmpeg exits.
    if progress_file and on_progress and duration > 0:
        _read_progress(progress_file, offset, duration, on_progress)


def _read_progress(
    path: Path,
    offset: int,
    duration: float,
    on_progress: Callable[[float], None],
) -> int:
    """Read whatever ffmpeg has appended since `offset`; return the new one."""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            handle.seek(offset)
            chunk = handle.read()
            offset = handle.tell()
    except OSError:
        return offset

    for line in chunk.splitlines():
        match = _PROGRESS_KEY_RE.match(line.strip())
        if not match:
            continue
        key, value = match.groups()
        if key == "out_time_ms":
            try:
                seconds = int(value) / 1_000_000
            except ValueError:
                continue
            on_progress(max(0.0, min(1.0, seconds / duration)))
        elif key == "progress" and value == "end":
            on_progress(1.0)
    return offset


def _no_window_kwargs() -> dict:
    """Keep ffmpeg from flashing a console window on Windows."""
    import sys

    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def iter_clip_jobs(clips: list[Clip]) -> Iterator[Clip]:
    """Yield the clips that are selected and free of validation errors."""
    for clip in clips:
        if clip.selected and clip.is_valid:
            yield clip


def build_convert_command(
    source: str | Path,
    output: str | Path,
    settings: EncodingSettings,
    *,
    ffmpeg_path: str = "",
    pass_number: int = 0,
    passlog_prefix: str = "",
) -> list[str]:
    """Transcode a whole file into another container.

    This is the second half of the cut-then-convert workflow: clips are cut to
    MP4 quickly for review, then the approved ones are converted to WebM for
    Commons. ``pass_number`` of 1 or 2 drives VP9 two-pass encoding.
    """
    exe = find_executable("ffmpeg", ffmpeg_path)
    command = [exe, "-hide_banner", "-nostdin"]
    command.append("-y" if settings.overwrite else "-n")
    command += _hardware_input_args(settings)
    command += ["-i", str(source)]

    if pass_number in (1, 2):
        command += _encode_args(settings)
        command += ["-pass", str(pass_number), "-passlogfile",
                    passlog_prefix or str(Path(output).with_suffix(""))]
        if pass_number == 1:
            # The first pass only gathers statistics; discard the output.
            command += ["-an", "-f", "null"]
            command += ["-progress", "pipe:1", "-nostats"]
            command.append(os.devnull)
            return command
    else:
        command += _encode_args(settings)

    if settings.threads:
        command += ["-threads", str(settings.threads)]
    command += list(settings.extra_args)
    command += ["-progress", "pipe:1", "-nostats"]
    command.append(str(output))
    return command


def convert_file(
    source: str | Path,
    output: str | Path,
    settings: EncodingSettings,
    *,
    ffmpeg_path: str = "",
    on_progress: Callable[[float], None] | None = None,
    on_log: Callable[[str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    duration: float | None = None,
) -> int:
    """Convert one file, running both VP9 passes when two-pass is enabled."""
    if duration is None:
        try:
            duration = probe(source).duration
        except FFmpegError:
            duration = 0.0

    # Two-pass is wired up for the libvpx encoders; AV1/x264 use CRF instead.
    two_pass = settings.vp9_two_pass and settings.video_codec.startswith("libvpx")
    if not two_pass:
        command = build_convert_command(source, output, settings, ffmpeg_path=ffmpeg_path)
        return run_command(
            command, duration, on_progress=on_progress,
            on_log=on_log, should_cancel=should_cancel,
        )

    prefix = str(Path(output).with_suffix("")) + "-passlog"
    for pass_number in (1, 2):
        # Report each pass across its own half of the progress bar.
        def scaled(value: float, _p: int = pass_number) -> None:
            if on_progress:
                on_progress((value + (_p - 1)) / 2)

        code = run_command(
            build_convert_command(
                source, output, settings, ffmpeg_path=ffmpeg_path,
                pass_number=pass_number, passlog_prefix=prefix,
            ),
            duration, on_progress=scaled, on_log=on_log, should_cancel=should_cancel,
        )
        if code != 0 or (should_cancel and should_cancel()):
            _cleanup_passlogs(prefix)
            return code
    _cleanup_passlogs(prefix)
    return 0


def _cleanup_passlogs(prefix: str) -> None:
    for leftover in Path(prefix).parent.glob(Path(prefix).name + "*"):
        try:
            leftover.unlink()
        except OSError:
            pass


def keyframe_interval(
    source: str | Path,
    *,
    around: float = 0.0,
    window: float = 60.0,
    ffprobe_path: str = "",
) -> float:
    """Seconds between keyframes near `around`, or 0.0 if it cannot be read.

    Stream copy can only cut on a keyframe, so this is what decides how far
    a copied clip drifts from the time asked for.
    """
    exe = find_executable("ffprobe", ffprobe_path)
    command = [
        exe, "-v", "error", "-select_streams", "v",
        "-show_entries", "packet=pts_time,flags",
        "-read_intervals", f"{max(0.0, around):.3f}%+{window:.0f}",
        "-of", "csv=p=0", str(source),
    ]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=30,
            **_no_window_kwargs(),
        )
    except (OSError, subprocess.SubprocessError):
        return 0.0

    times: list[float] = []
    for line in result.stdout.splitlines():
        stamp, _, flags = line.partition(",")
        if "K" not in flags:
            continue
        try:
            times.append(float(stamp))
        except ValueError:
            continue

    if len(times) < 2:
        return 0.0
    gaps = [b - a for a, b in zip(times, times[1:]) if b > a]
    if not gaps:
        return 0.0
    return sum(gaps) / len(gaps)


def copy_drift(
    starts: list[float],
    interval: float,
) -> tuple[float, float]:
    """Worst and average seconds a stream copy would start early.

    A copied cut snaps back to the preceding keyframe, so a clip whose start
    falls between keyframes opens on the tail of whatever came before.
    """
    if interval <= 0 or not starts:
        return 0.0, 0.0
    drifts = [start % interval for start in starts]
    return max(drifts), sum(drifts) / len(drifts)
