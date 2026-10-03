"""The transport bar."""

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from vcut.gui.player_bar import PlayerBar, RoundButton  # noqa: E402
from vcut.gui.theme import Theme, apply_theme  # noqa: E402


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def bar(qt_app):
    apply_theme(Theme.DARK)
    widget = PlayerBar()
    widget.set_duration(180_000)
    return widget


def test_the_times_follow_the_position(bar):
    bar.set_position(70_000)
    assert bar.position_label.text() == "00:01:10"
    assert bar.duration_label.text() == "00:03:00"


def test_the_scrubber_spans_the_video(bar):
    assert bar.scrubber.maximum() == 180_000


def test_play_and_pause_swap_the_icon(bar):
    bar.set_playing(True)
    assert bar.play_button._role == "pause"
    bar.set_playing(False)
    assert bar.play_button._role == "play"


def test_the_nudge_buttons_carry_their_amounts(bar, qt_app):
    seen = []
    bar.nudged.connect(seen.append)
    bar.back10_button.click()
    bar.forward1_button.click()
    assert seen == [-10_000, 1000]


def test_typing_a_timecode_requests_that_position(bar):
    seen = []
    bar.seek_requested.connect(seen.append)
    bar.jump_field.setText("00:01:05")
    bar._jump()
    assert seen == [65.0]


def test_a_short_timecode_is_accepted(bar):
    seen = []
    bar.seek_requested.connect(seen.append)
    bar.jump_field.setText("1:10")
    bar._jump()
    assert seen == [70.0]


def test_an_unparseable_timecode_is_flagged_and_ignored(bar):
    seen = []
    bar.seek_requested.connect(seen.append)
    bar.jump_field.setText("half past two")
    bar._jump()
    assert seen == []
    assert "border" in bar.jump_field.styleSheet()


def test_a_timecode_past_the_end_is_refused(bar):
    seen = []
    bar.seek_requested.connect(seen.append)
    bar.jump_field.setText("05:00:00")
    bar._jump()
    assert seen == []


def test_an_empty_jump_box_does_nothing(bar):
    seen = []
    bar.seek_requested.connect(seen.append)
    bar.jump_field.setText("   ")
    bar._jump()
    assert seen == []


def test_transport_buttons_stay_circular(qt_app):
    # A square play button means the global button rule has leaked in.
    button = RoundButton("play", "Play", diameter=52)
    assert button.width() == button.height() == 52
    assert "border-radius: 26px" in button.styleSheet()


def test_the_bar_restyles_for_each_theme(bar):
    apply_theme(Theme.LIGHT)
    bar.restyle()
    light = bar.styleSheet()
    apply_theme(Theme.DARK)
    bar.restyle()
    assert bar.styleSheet() != light
