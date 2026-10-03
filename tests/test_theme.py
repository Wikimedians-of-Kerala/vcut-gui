"""Light and dark themes."""

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from vcut.gui.theme import DARK, LIGHT, Theme, apply_theme, build_palette, resolve, stylesheet  # noqa: E402


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


def test_explicit_themes_resolve_to_themselves(qt_app):
    assert resolve(Theme.LIGHT) is Theme.LIGHT
    assert resolve(Theme.DARK) is Theme.DARK


def test_system_resolves_to_a_real_theme(qt_app):
    assert resolve(Theme.SYSTEM) in (Theme.LIGHT, Theme.DARK)


def test_the_dark_palette_is_darker_than_the_light_one(qt_app):
    light = build_palette(Theme.LIGHT).window().color()
    dark = build_palette(Theme.DARK).window().color()
    assert dark.lightness() < light.lightness()


def test_text_contrasts_with_its_background(qt_app):
    # Low contrast here is the bug that makes a theme unusable.
    for theme in (Theme.LIGHT, Theme.DARK):
        palette = build_palette(theme)
        window = palette.window().color().lightness()
        text = palette.windowText().color().lightness()
        assert abs(window - text) > 100


def test_applying_a_theme_changes_the_application_palette(qt_app):
    apply_theme(Theme.DARK)
    dark = qt_app.palette().window().color().name()
    apply_theme(Theme.LIGHT)
    light = qt_app.palette().window().color().name()
    assert dark != light
    assert dark == DARK["window"]
    assert light == LIGHT["window"]


def test_applying_a_theme_also_sets_a_stylesheet(qt_app):
    apply_theme(Theme.DARK)
    assert "QPushButton" in qt_app.styleSheet()


def test_the_stylesheet_gives_controls_room(qt_app):
    # The default Qt metrics are too tight; these are what was raised.
    sheet = stylesheet(Theme.DARK)
    assert "min-height: 32px" in sheet      # buttons
    assert "min-height: 30px" in sheet      # combo boxes and line edits


def test_the_current_step_is_styled_distinctly(qt_app):
    sheet = stylesheet(Theme.LIGHT)
    assert 'QPushButton#stepButton[current="true"]' in sheet
    assert "screenHeadingPanel" in sheet


def test_switching_theme_clears_the_icon_cache(qt_app):
    from vcut.gui import icons

    icons.icon("play")
    apply_theme(Theme.DARK)
    assert icons._cached.cache_info().currsize == 0
