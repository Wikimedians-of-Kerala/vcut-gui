"""How much work this machine can actually do at once.

Encoding video is the heaviest thing this program does, and the cost is not
small: one SVT-AV1 encode of 720p holds around 950 MB, measured, and AV1 at
1080p nearer 1.2 GB. Start more of those than the machine can hold and the
kernel kills them -- which arrives as "ffmpeg exited with code -11" and a
trail of 0-byte files, with nothing to say why.

So the number of simultaneous jobs is worked out from the machine rather
than fixed. Three facts decide it:

* **Memory.** The binding constraint in practice. Measured per encode, by
  codec and resolution; see :data:`MEMORY_COST`.
* **Cores.** ffmpeg already uses every core it is given, so two jobs on one
  machine finish no sooner than one after the other -- they just contend.
  Parallelism only pays when there are cores to spare.
* **Disk.** Running out mid-encode truncates the output, which looks like a
  crash.

Nothing here is a hard limit on ffmpeg itself; it decides how many we start.
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

#: Peak resident memory for one encode, in MB, by codec family, as
#: ``(fixed cost, cost per megapixel)``.
#:
#: Measured, not guessed: SVT-AV1 on this project's own footage, sampling
#: /proc RSS every 50 ms, gave 376 MB at 360p, 952 MB at 720p and 1219 MB at
#: 1080p. Most of it is a fixed allocation -- frame buffers and lookahead --
#: with a smaller per-pixel part, which is why the pair is a fixed cost plus
#: a slope rather than a single number.
#:
#: The constants deliberately sit *above* every measurement. Overestimating
#: costs a little parallelism; underestimating means the kernel kills the
#: encode, and that reaches the user as "exited with code -11".
#:
#: Two findings worth keeping, both measured and both contrary to the
#: obvious guess: ``-threads`` changes none of this (950/949/952 MB at 16, 4
#: and 2 threads), and neither does ``-preset`` (947 MB at preset 4). The
#: memory is frame buffers, so the only lever is how many run at once.
MEMORY_COST = {
    #             fixed MB, MB per megapixel
    "libsvtav1": (700.0, 280.0),
    "libaom-av1": (700.0, 280.0),
    "librav1e": (700.0, 280.0),
    # VP9 measured 294 MB at 720p -- about a third of AV1, which makes it
    # the format to suggest when memory is tight.
    "libvpx-vp9": (220.0, 90.0),
    "libvpx": (220.0, 90.0),
    "libtheora": (150.0, 60.0),
    "libx264": (180.0, 70.0),
    "libx265": (350.0, 150.0),
}

#: What to assume for an encoder not in the table: the heaviest thing known,
#: because guessing low is the failure that kills jobs.
DEFAULT_COST = (700.0, 280.0)

#: Leave this much memory for the desktop, the player and the rest of the
#: system. Encoding should never make the machine unusable.
HEADROOM_MB = 1536.0

#: Below this, do not start anything and say so.
MINIMUM_FREE_MB = 512.0

#: Refuse to start an encode with less free disk than this.
MINIMUM_DISK_MB = 1024.0


@dataclass(frozen=True)
class Machine:
    """What the computer has available right now."""

    total_memory_mb: float
    available_memory_mb: float
    cores: int
    free_disk_mb: float

    @property
    def usable_memory_mb(self) -> float:
        """Memory we are willing to spend on encoding."""
        return max(0.0, self.available_memory_mb - HEADROOM_MB)


def _read_meminfo() -> tuple[float, float] | None:
    """Total and available memory in MB, from /proc on Linux."""
    try:
        fields: dict[str, int] = {}
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            name, _, rest = line.partition(":")
            value = rest.strip().split(" ")[0]
            if value.isdigit():
                fields[name] = int(value)
        total = fields.get("MemTotal")
        available = fields.get("MemAvailable", fields.get("MemFree"))
        if total and available:
            return total / 1024, available / 1024
    except (OSError, ValueError):
        pass
    return None


def _windows_memory() -> tuple[float, float] | None:
    """Total and available memory in MB, through the Windows API."""
    try:
        import ctypes

        class Status(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = Status()
        status.dwLength = ctypes.sizeof(Status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return (
                status.ullTotalPhys / (1024 * 1024),
                status.ullAvailPhys / (1024 * 1024),
            )
    except Exception:  # noqa: BLE001 - any failure means "unknown"
        pass
    return None


def look(output_directory: str | Path = ".") -> Machine:
    """Measure the machine as it is now."""
    memory = _windows_memory() if sys.platform == "win32" else _read_meminfo()
    if memory is None:
        # Unknown memory: assume something modest rather than something
        # generous, so the fallback errs towards running one job at a time.
        memory = (4096.0, 2048.0)

    try:
        cores = len(os.sched_getaffinity(0))  # respects cgroup/taskset limits
    except AttributeError:
        cores = os.cpu_count() or 1

    try:
        free_disk = shutil.disk_usage(output_directory).free / (1024 * 1024)
    except OSError:
        free_disk = float("inf")

    return Machine(
        total_memory_mb=memory[0],
        available_memory_mb=memory[1],
        cores=cores,
        free_disk_mb=free_disk,
    )


def memory_for(codec: str, width: int = 0, height: int = 0) -> float:
    """Expected peak memory in MB for one encode."""
    fixed, per_megapixel = MEMORY_COST.get(codec, DEFAULT_COST)
    megapixels = (width * height) / 1_000_000 if width and height else 0.92
    return fixed + per_megapixel * megapixels


@dataclass(frozen=True)
class Budget:
    """How many encodes to run, and why that number."""

    jobs: int
    reason: str
    #: Set when nothing can safely run.
    blocked: str = ""

    def __bool__(self) -> bool:
        return self.jobs > 0 and not self.blocked


def plan(
    codec: str,
    *,
    width: int = 0,
    height: int = 0,
    wanted: int = 1,
    machine: Machine | None = None,
    output_directory: str | Path = ".",
) -> Budget:
    """Decide how many encodes may run at once.

    `wanted` is the most the caller would like; the answer is never more.
    """
    machine = machine or look(output_directory)

    if machine.free_disk_mb < MINIMUM_DISK_MB:
        return Budget(
            0, "", blocked=(
                f"Only {machine.free_disk_mb:.0f} MB of disk space is free. "
                f"Encoding needs room for the output; free up some space and "
                f"try again."
            ),
        )

    per_job = memory_for(codec, width, height)

    if machine.usable_memory_mb < MINIMUM_FREE_MB:
        return Budget(
            0, "", blocked=(
                f"Only {machine.available_memory_mb:.0f} MB of memory is free, "
                f"and one encode needs about {per_job:.0f} MB. Close some "
                f"applications and try again."
            ),
        )

    # Memory is the binding constraint in practice.
    by_memory = int(machine.usable_memory_mb // per_job)

    # Cores: ffmpeg already saturates what it is given, so running jobs
    # side by side buys far less than it looks like it should. Measured on
    # 16 cores, four at once encoded each clip in 1855 ms against 2259 ms
    # alone -- 18% faster per clip for four times the memory. That is a poor
    # trade when the downside of guessing wrong is the kernel killing the
    # run, so a job is given eight cores before a second one starts.
    by_cores = max(1, machine.cores // 8)

    jobs = max(1, min(wanted, by_memory, by_cores))

    # One job still has to fit. If it does not, say so rather than starting
    # something the kernel will kill.
    if by_memory < 1:
        return Budget(
            0, "", blocked=(
                f"One {codec} encode needs about {per_job:.0f} MB, and only "
                f"{machine.usable_memory_mb:.0f} MB can safely be used. Close "
                f"some applications, or choose a lighter format such as "
                f"WebM (VP9)."
            ),
        )

    if jobs < wanted:
        limit = "memory" if by_memory <= by_cores else "processor cores"
        reason = (
            f"{jobs} at a time (limited by {limit}: "
            f"{machine.usable_memory_mb:.0f} MB usable, {machine.cores} cores, "
            f"about {per_job:.0f} MB per encode)"
        )
    else:
        reason = f"{jobs} at a time"
    return Budget(jobs, reason)
