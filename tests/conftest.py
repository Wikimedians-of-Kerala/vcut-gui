"""Shared fixtures.

The important one makes the command-building tests independent of whether
FFmpeg is installed. They assert on argument order and never execute
anything, so requiring the binary only meant they passed on a developer's
machine and failed on a bare CI runner.
"""

import pytest

import vcut.ffmpeg


@pytest.fixture(autouse=True)
def ffmpeg_on_path(request, monkeypatch):
    """Pretend ffmpeg and ffprobe are installed, for tests that only build
    command lines.

    Marked ``needs_real_ffmpeg`` to opt out, for anything that actually runs
    it. The stub returns a plausible absolute path so assertions about the
    rest of the command are unaffected.
    """
    if request.node.get_closest_marker("needs_real_ffmpeg"):
        return

    def fake_which(name: str, configured: str = "") -> str:
        if configured:
            return configured
        return f"/usr/bin/{name}"

    monkeypatch.setattr(vcut.ffmpeg, "find_executable", fake_which)
