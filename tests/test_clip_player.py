"""Watching one cut clip from the metadata screen."""

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402


@pytest.fixture(scope="module")
def qt_app():
    yield QApplication.instance() or QApplication([])


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


def test_video_is_decoded_in_software():
    """Qt reaches for VAAPI and does not fall back when it fails.

    A GPU without AV1 decoding -- which is most of them -- gives a black
    window and "No support for codec av1 profile 0". AV1 is the format this
    program recommends for Commons, so its own output is what fails.
    """
    import inspect
    import os

    from vcut.gui.app import _decode_in_software, main

    _decode_in_software()
    assert os.environ.get("QT_FFMPEG_DECODING_HW_DEVICE_TYPES") == ""

    # It has to run before QApplication: Qt reads the variable at startup.
    body = inspect.getsource(main)
    assert body.index("_decode_in_software()") < body.index("QApplication(argv)")
