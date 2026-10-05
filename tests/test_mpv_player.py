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


def test_the_numeric_locale_is_forced_to_c():
    """libmpv aborts the whole process under any other numeric locale.

    "Non-C locale detected. This is not supported." is fatal, not a
    warning, and Qt sets the user's locale while starting -- so it has to
    be put back immediately before libmpv is created.
    """
    import inspect

    source = inspect.getsource(mpv_player.MpvPlayer._ensure)
    assert "LC_NUMERIC" in source
    assert 'setlocale' in source
    # Only the numeric part: dates and text stay the user's.
    assert "LC_ALL" not in source


def test_the_surface_is_wired_for_rendering(qt_app):
    """The pieces the render path needs, checked without a GPU.

    Actually playing a file needs a real GL context, which CI runners do
    not have -- a test that needs one either skips there or hangs the
    build, so it would not protect the release. What can be checked
    anywhere is that the object is built the way the render path requires,
    and that is what breaks when someone changes it.
    """
    surface = mpv_player.MpvSurface()
    try:
        # Nothing is created until there is both a GL context and an mpv:
        # Qt may bring up GL either side of the file being set.
        assert surface._context is None
        surface._build_context()
        assert surface._context is None, "built a context with no mpv"

        # Every entry point into the render path goes through one builder,
        # so whichever of the two arrives last starts the video.
        for method in (surface.initializeGL, surface.paintGL, surface.attach):
            assert callable(method)

        # Painting before there is anything to paint must not raise: Qt
        # calls paintGL as soon as the widget is shown.
        surface.paintGL()

        # And letting go twice is harmless, which is what closing a window
        # after an encode has already released the player does.
        surface.detach()
        surface.detach()
    finally:
        surface.deleteLater()


def test_the_xwayland_workaround_is_gone():
    """Forcing the whole program onto XWayland must not come back.

    It moved every window in the program onto a compatibility layer to
    solve a problem in one pane, and the render API removes the reason for
    it. The release order matters too: libmpv must not be left rendering
    into a context that has already been freed.
    """
    import inspect

    from vcut.gui import app as app_module

    assert not hasattr(app_module, "_embed_video_under_x11")
    assert "xcb" not in inspect.getsource(app_module)

    source = inspect.getsource(mpv_player)
    assert '"wid"' not in source
    assert 'options["vo"] = "libmpv"' in source

    release = inspect.getsource(mpv_player.MpvPlayer.release)
    assert release.index("detach()") < release.index("terminate()")


def test_windows_bundles_libmpv():
    """There is no Windows package to depend on, so the DLL must ship.

    Without it the packaged build shows a black rectangle for AV1, which is
    the format this program recommends -- its own output would not play.
    """
    from pathlib import Path

    script = Path("packaging/build-windows.ps1").read_text()
    assert "libmpv-2.dll" in script
    # The build must fail rather than quietly ship a player that cannot
    # decode anything.
    assert "throw" in script.split("Fetching libmpv")[1].split("Checking")[0]


def test_the_bundled_dll_can_be_found_at_runtime():
    """python-mpv loads the DLL through the ordinary Windows search path.

    A frozen bundle's own directory is not on it, so the program has to put
    it there before the import, or the shipped DLL is never found.
    """
    import inspect

    source = inspect.getsource(mpv_player._add_bundled_library_to_path)
    assert '"frozen"' in source
    assert "PATH" in source
    # Only Windows: elsewhere libmpv comes from the distribution.
    assert 'sys.platform != "win32"' in source

    # And it has to run before every attempt to import mpv.
    for function in (
        mpv_player.available,
        mpv_player.unavailable_reason,
        mpv_player.MpvPlayer._ensure,
    ):
        body = inspect.getsource(function)
        assert "_add_bundled_library_to_path()" in body
        assert body.index("_add_bundled_library_to_path()") < body.index("import mpv")


def test_the_release_refuses_a_windows_build_without_libmpv():
    """A silent miss here ships a player that cannot decode AV1.

    The DLL is fetched during the build rather than committed, so a change
    to the release it comes from, or a rename, would otherwise produce an
    archive that looks fine and shows a black rectangle.
    """
    from pathlib import Path

    workflow = Path(".github/workflows/release.yml").read_text()
    assert "libmpv-2" in workflow
    assert "AV1 will not play" in workflow


def test_the_opengl_modules_are_packaged():
    """PyInstaller cannot see either by following imports."""
    from pathlib import Path

    spec = Path("vcut-gui.spec").read_text()
    assert "PySide6.QtOpenGLWidgets" in spec
    # PyOpenGL picks its backend at runtime.
    assert "OpenGL.platform" in spec
