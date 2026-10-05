"""Watching one cut clip from the metadata screen."""

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402


@pytest.fixture(scope="module")
def qt_app():
    yield QApplication.instance() or QApplication([])


def _make_clip(path, codec: str) -> None:
    """Encode a one-second clip, or skip when ffmpeg is not installed.

    Checked before calling rather than after: a missing ffmpeg raises
    FileNotFoundError from subprocess, which is a test error rather than
    the skip it should be. CI runners have no ffmpeg -- the suite is meant
    to run offline, with no external tools.
    """
    import shutil
    import subprocess

    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg is not installed")

    made = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
         "-i", "testsrc2=size=160x90:rate=10:duration=1",
         "-c:v", codec, "-crf", "50", "-y", str(path)],
        capture_output=True,
    )
    if made.returncode != 0 or not path.is_file():
        pytest.skip(f"this ffmpeg cannot encode with {codec}")


def test_the_metadata_screen_offers_to_play_a_clip(qt_app):
    """The verify screen plays the whole recording; this plays one clip."""
    from vcut.gui.main_window import MainWindow

    screen = MainWindow().metadata_screen
    labels = [b.text() for b in screen.findChildren(QPushButton)]
    assert any("Play" in label for label in labels), labels


def test_a_missing_file_says_so_rather_than_failing(qt_app, tmp_path):
    from vcut.gui.clip_player_dialog import ClipPlayerDialog

    dialog = ClipPlayerDialog(str(tmp_path / "never-cut.webm"), "A session")
    assert "not there" in dialog.status.text().lower()
    # And there is nothing to press.
    assert not dialog.play_button.isEnabled()


def test_an_existing_file_is_opened(qt_app, tmp_path):
    from vcut.gui.clip_player_dialog import ClipPlayerDialog

    clip = tmp_path / "clip.webm"
    clip.write_bytes(b"not really a video, but it exists")

    dialog = ClipPlayerDialog(str(clip), "A session")
    assert dialog.play_button.isEnabled()
    # The size is worth showing: it is how an empty cut is spotted.
    assert "clip.webm" in dialog.status.text()


def test_closing_lets_go_of_the_file(qt_app, tmp_path):
    """A decoder left open holds memory the encoder wants."""
    from vcut.gui.clip_player_dialog import ClipPlayerDialog

    clip = tmp_path / "clip.webm"
    clip.write_bytes(b"x")

    dialog = ClipPlayerDialog(str(clip), "A session")
    dialog.accept()
    assert dialog.player.source().isEmpty()


def test_the_converted_copy_is_preferred(qt_app, tmp_path):
    """That is the file that would be uploaded, so it is the one to check."""
    from vcut.models import Clip

    cut = tmp_path / "cut.mp4"
    converted = tmp_path / "converted.webm"
    cut.write_bytes(b"x")
    converted.write_bytes(b"x")

    clip = Clip(programme="A talk", start_time="00:00:00", end_time="00:01:00")
    clip.output_path = str(cut)
    clip.converted_path = str(converted)

    assert clip.uploadable_path == str(converted)


def test_playing_without_a_selection_does_not_raise(qt_app):
    # Nothing selected is a fair state; it must explain, not crash.
    from vcut.gui.main_window import MainWindow

    screen = MainWindow().metadata_screen
    screen.table.setCurrentCell(-1, -1)
    # No clips loaded either, so the guard is what stops it.
    assert screen.table.currentRow() < 0


# -- moving between clips --------------------------------------------------


def test_the_player_lists_every_clip(qt_app, tmp_path):
    """Checking a day of cuts means moving between them."""
    from vcut.gui.clip_player_dialog import ClipPlayerDialog
    from vcut.models import Clip

    video = tmp_path / "clip.webm"
    video.write_bytes(b"x")

    clips = []
    for name in ("One", "Two", "Three"):
        clip = Clip(programme=name, start_time="00:00:00", end_time="00:01:00")
        clip.output_path = str(video)
        clips.append(clip)

    dialog = ClipPlayerDialog(str(video), "One", clips=clips, current=0)
    assert dialog.chooser is not None
    assert dialog.chooser.count() == 3
    assert dialog.chooser.currentIndex() == 0
    # Numbered, so position in the day is visible.
    assert dialog.chooser.itemText(0).startswith("01.")


def test_an_uncut_clip_is_listed_but_cannot_be_chosen(qt_app, tmp_path):
    # Listed so the gap in the day is visible; disabled so it cannot be
    # selected only to fail.
    from vcut.gui.clip_player_dialog import ClipPlayerDialog
    from vcut.models import Clip

    video = tmp_path / "clip.webm"
    video.write_bytes(b"x")

    cut = Clip(programme="Cut", start_time="00:00:00", end_time="00:01:00")
    cut.output_path = str(video)
    uncut = Clip(programme="Uncut", start_time="00:01:00", end_time="00:02:00")

    dialog = ClipPlayerDialog(str(video), "Cut", clips=[cut, uncut], current=0)
    assert "not cut" in dialog.chooser.itemText(1)
    assert not dialog.chooser.model().item(1).isEnabled()


def test_switching_clips_opens_the_other_file(qt_app, tmp_path):
    from vcut.gui.clip_player_dialog import ClipPlayerDialog
    from vcut.models import Clip

    first = tmp_path / "first.webm"
    second = tmp_path / "second.webm"
    first.write_bytes(b"x")
    second.write_bytes(b"yy")

    clips = []
    for name, path in (("One", first), ("Two", second)):
        clip = Clip(programme=name, start_time="00:00:00", end_time="00:01:00")
        clip.output_path = str(path)
        clips.append(clip)

    dialog = ClipPlayerDialog(str(first), "One", clips=clips, current=0)
    dialog.chooser.setCurrentIndex(1)
    assert "second.webm" in dialog.windowTitle()


def test_without_a_list_there_is_no_chooser(qt_app, tmp_path):
    from vcut.gui.clip_player_dialog import ClipPlayerDialog

    video = tmp_path / "clip.webm"
    video.write_bytes(b"x")

    dialog = ClipPlayerDialog(str(video), "Just this one")
    assert dialog.chooser is None


def test_an_av1_clip_is_sent_to_the_system_player(qt_app, tmp_path):
    """Qt ships no AV1 decoder, and AV1 is what Commons wants.

    Measured when this was found: the same three seconds delivered 0 frames
    as AV1 and 87 as VP9 or H.264, with Qt reporting PlayingState and no
    error -- a black rectangle and nothing to explain it.

    Decoding it in-process was tried and abandoned: seeking and audio were
    both poor enough that the desktop's own player is the better answer.
    """
    from vcut.gui.clip_player_dialog import playable_here

    from vcut.gui import mpv_player

    clip = tmp_path / "clip.webm"
    _make_clip(clip, "libsvtav1")

    # With libmpv the app plays AV1 itself; without it, the desktop's own
    # player is the honest answer.
    assert playable_here(clip) is mpv_player.available()


def test_a_playable_codec_is_not_blocked(qt_app, tmp_path):
    from vcut.gui.clip_player_dialog import ClipPlayerDialog

    clip = tmp_path / "clip.mp4"
    _make_clip(clip, "libx264")

    dialog = ClipPlayerDialog(str(clip), "An H.264 clip")
    assert dialog.play_button.isEnabled()
    assert "cannot decode" not in dialog.status.text()


# -- choosing where to play ------------------------------------------------


def test_an_ordinary_codec_always_plays_in_the_window(qt_app, tmp_path):
    from vcut.gui.clip_player_dialog import playable_here

    clip = tmp_path / "clip.mp4"
    _make_clip(clip, "libx264")

    assert playable_here(clip) is True


def test_an_unreadable_file_is_attempted_rather_than_refused(tmp_path):
    # A probe failure should not stop the user trying.
    from vcut.gui.clip_player_dialog import playable_here

    assert playable_here(tmp_path / "nothing-here.webm") is True


def test_the_verify_screen_warns_about_an_av1_source(qt_app, tmp_path):
    """The same fault, on the screen where the picture matters most.

    Cutting is unaffected -- that is the system ffmpeg's job -- so the
    message says what still works rather than only what does not.
    """
    from vcut.ffmpeg import probe
    from vcut.gui.main_window import MainWindow

    source = tmp_path / "source.webm"
    _make_clip(source, "libsvtav1")

    from vcut.gui import mpv_player

    window = MainWindow()
    window.state.set_source(str(source), probe(source))
    text = window.verify_screen.summary.text()

    if mpv_player.available():
        # libmpv decodes AV1, so there is nothing to warn about.
        assert "cannot show" not in text
    else:
        assert "AV1" in text
        assert "black" in text.lower()
        # And it must say cutting still works, and how to fix the picture.
        assert "cutting" in text.lower()
        assert "libmpv" in text.lower() or "python-mpv" in text.lower()
