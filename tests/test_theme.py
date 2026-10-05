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
    # The default Qt metrics are too tight. Buttons and fields share one
    # height so a field beside its button lines up.
    from vcut.gui.theme import FIELD_HEIGHT

    sheet = stylesheet(Theme.DARK)
    assert FIELD_HEIGHT >= 28
    assert f"min-height: {FIELD_HEIGHT}px" in sheet


def test_the_current_step_is_styled_distinctly(qt_app):
    sheet = stylesheet(Theme.LIGHT)
    assert 'QPushButton#stepButton[current="true"]' in sheet
    assert "screenHeadingPanel" in sheet


def test_switching_theme_clears_the_icon_cache(qt_app):
    from vcut.gui import icons

    icons.icon("play")
    apply_theme(Theme.DARK)
    assert icons._cached.cache_info().currsize == 0


# -- control affordances ---------------------------------------------------


def test_dropdowns_get_a_visible_arrow(qt_app):
    # Styling the drop-down at all stops Qt drawing its own arrow, so the
    # stylesheet must supply one or a combo looks like a plain text field.
    sheet = stylesheet(Theme.DARK)
    assert "QComboBox::down-arrow" in sheet
    assert "image: url(" in sheet


def test_the_dropdown_panel_is_distinguishable(qt_app):
    sheet = stylesheet(Theme.DARK)
    assert "QComboBox::drop-down" in sheet
    assert "border-left" in sheet


def test_spin_boxes_get_visible_steppers(qt_app):
    sheet = stylesheet(Theme.DARK)
    assert "QSpinBox::up-arrow" in sheet
    assert "QSpinBox::down-arrow" in sheet


def test_the_arrow_images_are_written_and_differ(qt_app):
    from pathlib import Path

    from vcut.gui.theme import DARK, _arrow_icon

    down = _arrow_icon(DARK["text"])
    up = _arrow_icon(DARK["text"], up=True)
    assert Path(down).is_file()
    assert Path(up).is_file()
    assert down != up
    assert Path(down).read_bytes() != Path(up).read_bytes()


def test_arrow_images_are_tinted_per_theme(qt_app):
    from vcut.gui.theme import DARK, LIGHT, _arrow_icon

    assert _arrow_icon(DARK["text"]) != _arrow_icon(LIGHT["text"])


def test_the_step_bar_carries_the_screen_description(qt_app):
    # The description used to sit in a banner of its own, costing every
    # screen a row of height.
    from vcut.gui.main_window import STEPS, StepBar

    bar = StepBar()
    bar.set_current(2)
    assert STEPS[2][1] in bar.caption.text()
    assert "Step 3 of 4" in bar.caption.text()


# -- consistent spacing ----------------------------------------------------


def test_fields_are_padded_less_inside_than_the_gap_around_them(qt_app):
    # The reported bug: generous padding inside a field with a tight gap
    # between rows made the text look closer to other rows than to its own
    # border.
    from vcut.gui.theme import FIELD_PADDING_V, SPACE_ROW

    assert FIELD_PADDING_V * 2 < SPACE_ROW


def test_the_spacing_scale_increases(qt_app):
    from vcut.gui.theme import SPACE_EDGE, SPACE_GROUP, SPACE_ROW, SPACE_TIGHT

    assert SPACE_TIGHT < SPACE_ROW < SPACE_GROUP <= SPACE_EDGE


def test_fields_and_buttons_share_a_height(qt_app):
    # A row of a field beside its button should line up.
    sheet = stylesheet(Theme.DARK)
    assert sheet.count("min-height: 30px") >= 2


def test_a_note_sits_with_its_field_not_in_its_own_row(qt_app):
    from PySide6.QtWidgets import QLabel, QLineEdit

    from vcut.gui.widgets import with_note

    field = QLineEdit()
    note = QLabel("explanation")
    holder = with_note(field, note)
    assert field.parent() is holder
    assert note.parent() is holder
    assert holder.layout().spacing() < 8


def test_with_note_accepts_several_notes(qt_app):
    from PySide6.QtWidgets import QCheckBox, QLabel, QLineEdit

    from vcut.gui.widgets import with_note

    holder = with_note(QLineEdit(), QCheckBox("option"), QLabel("hint"))
    assert holder.layout().count() == 3


def test_the_setup_form_has_no_orphan_rows(qt_app):
    # Every note belongs to a field; an addRow("", ...) would float between
    # two rows instead.
    from pathlib import Path

    source = Path("src/vcut/gui/screen_setup.py").read_text(encoding="utf-8")
    assert 'addRow("", ' not in source


def test_stream_copy_states_what_it_costs_on_this_file(qt_app):
    """The warning must carry the measured figure, not "several seconds".

    Copying is hundreds of times faster, and on a conference recording the
    drift is usually harmless, so the user needs the real number to judge.
    """
    from vcut.ffmpeg import CutMode, MediaInfo, OutputFormat
    from vcut.gui.main_window import MainWindow
    from vcut.models import Clip

    window = MainWindow()
    screen = window.setup_screen
    window.state.set_source(
        "day1.mp4",
        MediaInfo(duration=32540.0, width=1280, height=720, fps=30.0,
                  keyframe_interval=5.0),
    )
    window.state.clips[:] = [
        Clip(programme="One", start_time="00:10:59", end_time="00:33:34"),
        Clip(programme="Two", start_time="00:33:52", end_time="00:52:51"),
    ]

    # Re-render after the clips land: set_source replaces the list.
    screen.cut_box.setCurrentIndex(screen.cut_box.findData(CutMode.SMART))
    # Stream copy only applies to an MP4 target: it cannot change the codec,
    # so for WebM the note says that instead.
    screen.format_box.setCurrentIndex(screen.format_box.findData(OutputFormat.MP4.value))
    screen.cut_box.setCurrentIndex(screen.cut_box.findData(CutMode.COPY))
    text = screen.cut_hint.text()

    assert "5s apart" in text, text
    assert "early" in text
    assert "faster" in text


def test_an_unmeasured_file_does_not_invent_a_figure(qt_app):
    from vcut.ffmpeg import CutMode, MediaInfo, OutputFormat
    from vcut.gui.main_window import MainWindow

    window = MainWindow()
    screen = window.setup_screen
    window.state.set_source("day1.mp4", MediaInfo(duration=600.0))
    window.state.clips = []

    screen.format_box.setCurrentIndex(screen.format_box.findData(OutputFormat.MP4.value))
    screen.cut_box.setCurrentIndex(screen.cut_box.findData(CutMode.COPY))
    text = screen.cut_hint.text()

    assert "keyframes are" not in text
    assert "faster" in text


def test_an_unparseable_row_does_not_break_the_hint(qt_app):
    from vcut.ffmpeg import CutMode, MediaInfo, OutputFormat
    from vcut.gui.main_window import MainWindow
    from vcut.models import Clip

    window = MainWindow()
    screen = window.setup_screen
    window.state.set_source(
        "day1.mp4", MediaInfo(duration=600.0, keyframe_interval=5.0)
    )
    window.state.clips = [Clip(programme="x", start_time="nonsense", end_time="")]

    screen.cut_box.setCurrentIndex(screen.cut_box.findData(CutMode.COPY))
    assert screen.cut_hint.text()
