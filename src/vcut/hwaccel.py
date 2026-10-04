"""Hardware-accelerated encoding.

A GPU can encode video far faster than a CPU, but only for the codecs its
silicon implements, and that varies by chip. Listing an encoder in ffmpeg
proves nothing: ``av1_vaapi`` exists in most builds and fails on hardware
without an AV1 block. So every encoder offered here is probed by actually
running it once, and the result cached.

The honest summary for Wikimedia work: Commons accepts only AV1, VP9 and
Theora, and AV1/VP9 hardware encoders are still rare. On most machines the
GPU will speed up MP4 review cuts and leave the Commons conversion on the
CPU. The app says so rather than implying otherwise.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from enum import Enum

from .ffmpeg import FFmpegError, child_environment, find_executable


class Backend(str, Enum):
    """A way of reaching the GPU. Which exist depends on the platform."""

    NONE = "none"
    NVENC = "nvenc"          # NVIDIA, all platforms
    QSV = "qsv"              # Intel Quick Sync
    VAAPI = "vaapi"          # Linux, AMD and Intel
    AMF = "amf"              # AMD, Windows
    VIDEOTOOLBOX = "videotoolbox"   # macOS

    @property
    def label(self) -> str:
        return {
            Backend.NONE: "CPU only",
            Backend.NVENC: "NVIDIA (NVENC)",
            Backend.QSV: "Intel Quick Sync",
            Backend.VAAPI: "VAAPI",
            Backend.AMF: "AMD (AMF)",
            Backend.VIDEOTOOLBOX: "Apple VideoToolbox",
        }[self]


#: Encoder name per backend and codec. ``None`` means the backend has no
#: encoder for that codec at all.
ENCODERS: dict[Backend, dict[str, str]] = {
    Backend.NVENC: {"h264": "h264_nvenc", "hevc": "hevc_nvenc", "av1": "av1_nvenc"},
    Backend.QSV: {"h264": "h264_qsv", "hevc": "hevc_qsv",
                  "av1": "av1_qsv", "vp9": "vp9_qsv"},
    Backend.VAAPI: {"h264": "h264_vaapi", "hevc": "hevc_vaapi",
                    "av1": "av1_vaapi", "vp9": "vp9_vaapi"},
    Backend.AMF: {"h264": "h264_amf", "hevc": "hevc_amf", "av1": "av1_amf"},
    Backend.VIDEOTOOLBOX: {"h264": "h264_videotoolbox",
                           "hevc": "hevc_videotoolbox"},
}

#: Codecs Wikimedia Commons will accept. Hardware support for these is the
#: thing that actually matters for uploading.
COMMONS_CODECS = ("av1", "vp9")


@dataclass
class Encoder:
    """One hardware encoder, and whether it really runs."""

    backend: Backend
    codec: str
    name: str
    works: bool = False
    detail: str = ""

    @property
    def commons_ready(self) -> bool:
        return self.codec in COMMONS_CODECS

    @property
    def label(self) -> str:
        return f"{self.codec.upper()} on {self.backend.label}"


@dataclass
class Capabilities:
    """What this machine can do, as measured rather than advertised."""

    encoders: list[Encoder] = field(default_factory=list)
    device: str = ""
    probed_at: float = 0.0
    error: str = ""

    def working(self, codec: str = "") -> list[Encoder]:
        found = [e for e in self.encoders if e.works]
        return [e for e in found if e.codec == codec] if codec else found

    def best_for(self, codec: str) -> Encoder | None:
        candidates = self.working(codec)
        return candidates[0] if candidates else None

    @property
    def any_hardware(self) -> bool:
        return bool(self.working())

    @property
    def commons_hardware(self) -> list[Encoder]:
        """Hardware encoders for formats Commons actually accepts."""
        return [e for e in self.working() if e.commons_ready]

    def summary(self) -> str:
        if self.error:
            return self.error
        if not self.any_hardware:
            return "No working GPU encoder found — encoding will use the CPU."

        names = ", ".join(sorted({e.codec.upper() for e in self.working()}))
        backend = self.working()[0].backend.label
        if self.commons_hardware:
            return (
                f"{backend} can encode {names}. The Commons formats are "
                f"covered, so converting will use the GPU."
            )
        return (
            f"{backend} can encode {names}, but not the formats Commons "
            f"accepts (AV1 or VP9). The GPU will speed up MP4 review cuts; "
            f"converting for Commons stays on the CPU."
        )


def default_device() -> str:
    """The render node to use for VAAPI, on Linux."""
    if sys.platform != "linux":
        return ""
    for node in ("/dev/dri/renderD128", "/dev/dri/renderD129"):
        if os.path.exists(node):
            return node
    return ""


def _available_encoder_names(ffmpeg_path: str = "") -> set[str]:
    from .ffmpeg import available_encoders

    return available_encoders(ffmpeg_path)


def _probe_command(encoder: Encoder, device: str, exe: str) -> list[str]:
    """A two-frame encode to null — the cheapest honest test."""
    command = [exe, "-hide_banner", "-v", "error"]
    if encoder.backend is Backend.VAAPI:
        command += ["-vaapi_device", device or default_device()]
    command += ["-f", "lavfi", "-i", "testsrc2=size=320x240:rate=25:duration=0.2"]
    if encoder.backend is Backend.VAAPI:
        command += ["-vf", "format=nv12,hwupload"]
    command += ["-c:v", encoder.name, "-f", "null", "-"]
    return command


def probe(ffmpeg_path: str = "", device: str = "", timeout: float = 20.0) -> Capabilities:
    """Measure which hardware encoders actually run on this machine."""
    caps = Capabilities(device=device or default_device(), probed_at=time.time())

    try:
        exe = find_executable("ffmpeg", ffmpeg_path)
    except FFmpegError as exc:
        caps.error = str(exc)
        return caps

    present = _available_encoder_names(ffmpeg_path)
    for backend, codecs in ENCODERS.items():
        for codec, name in codecs.items():
            if name not in present:
                continue
            encoder = Encoder(backend=backend, codec=codec, name=name)
            try:
                result = subprocess.run(
                    _probe_command(encoder, caps.device, exe),
                    capture_output=True, env=child_environment(), text=True, timeout=timeout, check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                encoder.detail = str(exc)
                caps.encoders.append(encoder)
                continue

            encoder.works = result.returncode == 0
            if not encoder.works:
                # Keep the first line; it usually names the missing profile.
                first = (result.stderr or "").strip().splitlines()
                encoder.detail = first[0][:200] if first else "failed"
            caps.encoders.append(encoder)

    return caps


# -- caching ---------------------------------------------------------------

#: Probing spawns a process per encoder, so the answer is cached between runs.
CACHE_TTL = 30 * 24 * 3600


def _cache_file():
    from .settings import cache_directory

    return cache_directory() / "hwaccel.json"


def load_cached(max_age: float = CACHE_TTL) -> Capabilities | None:
    path = _cache_file()
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if time.time() - payload.get("probed_at", 0) > max_age:
        return None

    caps = Capabilities(
        device=payload.get("device", ""),
        probed_at=payload.get("probed_at", 0.0),
        error=payload.get("error", ""),
    )
    for raw in payload.get("encoders", []):
        try:
            caps.encoders.append(Encoder(
                backend=Backend(raw["backend"]), codec=raw["codec"],
                name=raw["name"], works=bool(raw.get("works")),
                detail=raw.get("detail", ""),
            ))
        except (KeyError, ValueError):
            continue
    return caps


def save_cached(caps: Capabilities) -> None:
    payload = {
        "probed_at": caps.probed_at,
        "device": caps.device,
        "error": caps.error,
        "encoders": [
            {"backend": e.backend.value, "codec": e.codec, "name": e.name,
             "works": e.works, "detail": e.detail}
            for e in caps.encoders
        ],
    }
    try:
        _cache_file().write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:
        pass


def detect(*, force: bool = False, ffmpeg_path: str = "") -> Capabilities:
    """Cached capability detection."""
    if not force:
        cached = load_cached()
        if cached is not None:
            return cached
    caps = probe(ffmpeg_path)
    save_cached(caps)
    return caps
