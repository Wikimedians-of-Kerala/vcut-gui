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


def test_the_player_is_released_before_encoding(qt_app=None):
    """Qt Multimedia keeps its own FFmpeg in this process.

    It announces "Using Qt multimedia with FFmpeg version 7.1.5" while the
    system ffmpeg may be 9.x, so a long file held open through the player
    while a child ffmpeg runs is a configuration worth avoiding.
    """
    from vcut.gui import workers

    called: list[str] = []
    workers.before_encoding(lambda: called.append("released"))

    try:
        with workers.encoding_slot("libx264", width=640, height=360):
            pass
    except workers.EncodingBusy:
        pass

    assert called, "nothing was released before the encode"


def test_a_failing_release_does_not_block_the_job():
    # Letting go of the player is a precaution, not a precondition.
    from vcut.gui import workers

    def explode() -> None:
        raise RuntimeError("the widget is gone")

    workers.before_encoding(explode)
    with workers.encoding_slot("libx264", width=640, height=360):
        pass


def test_releasing_swaps_in_the_placeholder():
    """The pane must not just go black, which reads as a broken player."""
    from PySide6.QtCore import QUrl
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from vcut.ffmpeg import MediaInfo
    from vcut.gui.main_window import MainWindow

    window = MainWindow()
    screen = window.verify_screen
    window.state.set_source("day1.mp4", MediaInfo(duration=600.0))

    assert screen.video_stack.currentWidget() is screen.video

    screen.release_player()
    assert screen.video_stack.currentWidget() is screen.video_placeholder
    assert screen.player.source() == QUrl(), "the file was not let go"

    screen.restore_player()
    assert screen.video_stack.currentWidget() is screen.video


def test_the_placeholder_says_why_it_is_there():
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from vcut.gui.main_window import MainWindow

    text = MainWindow().verify_screen.video_placeholder.text().lower()
    assert "encoding" in text


def test_releasing_clears_the_source_not_merely_stops():
    """stop() keeps the decoder; clearing the source is what frees it.

    Measured on a nine-hour recording: stop() alone recovered 5 MB, while
    clearing the source recovered 71 MB.
    """
    import inspect

    from vcut.gui.screen_verify import VerifyScreen

    source = inspect.getsource(VerifyScreen.release_player)
    assert "setSource" in source, "the file is never let go"


def test_the_player_comes_back_when_encoding_ends():
    """Releasing is only half of it; the pane must not stay grey."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from vcut.ffmpeg import MediaInfo
    from vcut.gui import workers
    from vcut.gui.main_window import MainWindow

    window = MainWindow()
    screen = window.verify_screen
    window.state.set_source("day1.mp4", MediaInfo(duration=600.0))

    with workers.encoding_slot("libx264", width=640, height=360):
        app.processEvents()
        assert screen.video_stack.currentWidget() is screen.video_placeholder

    app.processEvents()
    assert screen.video_stack.currentWidget() is screen.video


def test_the_hooks_cross_threads_safely():
    # Qt widgets may only be touched from the GUI thread, so the worker
    # emits a queued signal rather than calling the screen directly.
    import inspect

    from vcut.gui.screen_verify import VerifyScreen

    source = inspect.getsource(VerifyScreen)
    assert "_release_requested" in source
    assert "QueuedConnection" in source


def test_the_convert_button_does_not_pass_its_checked_state_as_rows():
    """clicked carries a bool, which would arrive as the list of rows.

    It crashed with "TypeError: 'bool' object is not iterable" the moment
    Convert for Commons was pressed.
    """
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from vcut.gui.main_window import MainWindow

    window = MainWindow()
    screen = window.metadata_screen

    # Should be a no-op with nothing loaded, not an exception.
    screen._convert(rows=True)
    screen._convert(rows=False)
    screen.convert_button.click()
