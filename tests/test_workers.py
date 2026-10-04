"""Running encoding jobs."""

import threading

import pytest

pytest.importorskip("PySide6")

from vcut.gui.workers import (  # noqa: E402
    EncodingBusy,
    encoding_in_progress,
    encoding_slot,
)


def test_nothing_is_encoding_to_begin_with():
    assert not encoding_in_progress()


def test_a_second_job_is_refused_while_one_runs():
    """One encode at a time.

    A single SVT-AV1 encode of 720p holds around 960 MB and already uses
    every core. Two at once finish no sooner and double the memory; on a
    machine with less headroom than the sum the kernel kills them, which
    reaches the user as "ffmpeg exited with code -11" and 0-byte files.
    """
    held = threading.Event()
    release = threading.Event()
    refused: list[str] = []

    def first() -> None:
        with encoding_slot():
            held.set()
            release.wait(5)

    worker = threading.Thread(target=first, daemon=True)
    worker.start()
    assert held.wait(2), "the first job never started"

    assert encoding_in_progress()
    try:
        with encoding_slot():
            pytest.fail("a second job was allowed to start")
    except EncodingBusy as exc:
        refused.append(str(exc))

    release.set()
    worker.join(timeout=5)

    assert refused and "already running" in refused[0]
    assert not encoding_in_progress()


def test_the_slot_is_released_even_when_the_job_raises():
    # A crash mid-encode must not wedge the application for the session.
    with pytest.raises(ValueError):
        with encoding_slot():
            raise ValueError("boom")

    assert not encoding_in_progress()
    with encoding_slot():
        pass


def test_refusing_names_what_to_do():
    held = threading.Event()
    release = threading.Event()

    def first() -> None:
        with encoding_slot():
            held.set()
            release.wait(5)

    worker = threading.Thread(target=first, daemon=True)
    worker.start()
    held.wait(2)

    with pytest.raises(EncodingBusy) as caught:
        with encoding_slot():
            pass

    message = str(caught.value)
    release.set()
    worker.join(timeout=5)

    # The user needs to know it is not an error in their file.
    assert "wait" in message.lower() or "cancel" in message.lower()


def test_both_kinds_of_job_share_the_slot():
    # Splitting and converting are both encoding, so one must exclude the
    # other -- otherwise a convert started during a split runs alongside it.
    import inspect

    from vcut.gui.workers import ConvertWorker, CutWorker

    for worker in (CutWorker, ConvertWorker):
        source = inspect.getsource(worker.run)
        assert "encoding_slot" in source, worker.__name__
