"""The libmpv-backed player."""

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from vcut.gui import mpv_player  # noqa: E402


@pytest.fixture(scope="module")
def qt_app():
    yield QApplication.instance() or QApplication([])


def test_it_reports_whether_it_can_be_used():
    # Either answer is fine; what matters is that asking never raises.
    assert isinstance(mpv_player.available(), bool)


def test_an_unavailable_reason_says_what_to_install():
    if mpv_player.available():
        assert mpv_player.unavailable_reason() == ""
        return
    reason = mpv_player.unavailable_reason().lower()
    # A missing library and a missing binding need different fixes.
    assert "mpv" in reason
    assert "install" in reason or "dll" in reason


def test_it_presents_the_interface_the_screens_use():
    """The screens must not care which player they got.

    This is an adapter, not a player: everything the verify screen does --
    frame stepping, shuttling, jumping, zooming -- is built on setPosition
    in the screen itself, so the surface below stays small.
    """
    for name in (
        "setSource", "source", "play", "pause", "stop",
        "position", "duration", "setPosition", "playbackState",
        "setAudioOutput", "setVideoOutput",
    ):
        assert hasattr(mpv_player.MpvPlayer, name), name

    for signal in ("positionChanged", "durationChanged", "errorOccurred"):
        assert hasattr(mpv_player.MpvPlayer, signal), signal


def test_it_can_be_built_and_released_without_a_file(qt_app):
    # Constructing must not start libmpv: the screen builds one whether or
    # not a video is ever loaded.
    player = mpv_player.MpvPlayer()
    assert player.position() == 0
    assert player.duration() == 0
    player.release()


def test_releasing_twice_is_harmless(qt_app):
    player = mpv_player.MpvPlayer()
    player.release()
    player.release()


def test_an_empty_source_clears_rather_than_raising(qt_app):
    from PySide6.QtCore import QUrl

    player = mpv_player.MpvPlayer()
    player.setSource(QUrl())
    assert player.position() == 0
    player.release()


def test_a_seek_before_loading_is_remembered(qt_app):
    """Restoring a position after an encode depends on this.

    libmpv drops a seek issued before the file is open, so the position
    came back as 0 and the user lost their place.
    """
    player = mpv_player.MpvPlayer()
    player.setPosition(90_000)
    assert player._pending_seek_ms == 90_000
    player.release()


def test_the_verify_screen_uses_libmpv_when_it_is_there(qt_app):
    from vcut.gui.main_window import MainWindow

    screen = MainWindow().verify_screen
    if mpv_player.available():
        assert isinstance(screen.player, mpv_player.MpvPlayer)
        # And draws into a plain native widget, not a QVideoWidget.
        assert screen._video_surface() is screen.mpv_surface
    else:
        from PySide6.QtMultimedia import QMediaPlayer

        assert isinstance(screen.player, QMediaPlayer)
        assert screen._video_surface() is screen.video
