"""Button icons."""

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

from vcut.gui import icons  # noqa: E402


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


def test_every_role_resolves_to_an_icon(qt_app):
    missing = [role for role in icons.ICON_NAMES if icons.icon(role).isNull()]
    assert missing == []


def test_an_unknown_role_gives_an_empty_icon(qt_app):
    assert icons.icon("no-such-role").isNull()


def test_applying_an_icon_keeps_the_button_text(qt_app):
    button = QPushButton("Split the video")
    icons.apply(button, "cut")
    assert button.text() == "Split the video"
    assert not button.icon().isNull()


def test_applying_an_unknown_role_leaves_the_button_alone(qt_app):
    button = QPushButton("Something")
    icons.apply(button, "no-such-role")
    assert button.icon().isNull()


def test_icons_are_cached_between_calls(qt_app):
    icons.clear_cache()
    first = icons.icon("play")
    before = icons._cached.cache_info().hits
    icons.icon("play")
    assert icons._cached.cache_info().hits == before + 1
    assert not first.isNull()


def test_the_cache_can_be_cleared(qt_app):
    icons.icon("play")
    icons.clear_cache()
    assert icons._cached.cache_info().currsize == 0


def test_the_player_roles_are_all_present():
    # The transport controls are the icons users recognise at a glance.
    for role in ("play", "pause", "back10", "forward10", "back1", "forward1",
                 "go-start", "go-end", "preview"):
        assert role in icons.ICON_NAMES


def test_without_qtawesome_everything_degrades_to_no_icon(qt_app, monkeypatch):
    monkeypatch.setattr(icons, "available", lambda: False)
    assert icons.icon("play").isNull()
    button = QPushButton("Play")
    icons.apply(button, "play")
    assert button.icon().isNull()
    assert button.text() == "Play"
