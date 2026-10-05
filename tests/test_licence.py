"""Choosing a licence, and the date override beside it."""

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from vcut.gui.licence_dialog import LICENCES  # noqa: E402


@pytest.fixture(scope="module")
def qt_app():
    yield QApplication.instance() or QApplication([])


def test_the_usual_licences_are_offered():
    """The four a conference team actually reaches for."""
    templates = {licence.template for licence in LICENCES}
    assert "{{Cc-by-sa-4.0}}" in templates     # the Wikimedia default
    assert "{{Cc-by-4.0}}" in templates
    assert "{{Cc-zero}}" in templates          # CC0
    assert "{{PD-self}}" in templates          # public domain


def test_every_licence_is_a_template_call():
    # A bare name would render as text rather than a licence box.
    for licence in LICENCES:
        assert licence.template.startswith("{{")
        assert licence.template.endswith("}}")


def test_every_licence_explains_itself():
    # The difference between BY and BY-SA is the whole decision.
    for licence in LICENCES:
        assert licence.name
        assert len(licence.note) > 30, licence.name


def test_the_recommended_one_is_first():
    assert LICENCES[0].template == "{{Cc-by-sa-4.0}}"


def test_the_picker_opens_on_the_current_licence(qt_app):
    from vcut.gui.licence_dialog import LicenceDialog

    dialog = LicenceDialog("{{Cc-zero}}")
    assert dialog.chosen() == "{{Cc-zero}}"


def test_an_unknown_licence_does_not_break_the_picker(qt_app):
    # An event-specific permission template is a real and valid case.
    from vcut.gui.licence_dialog import LicenceDialog

    dialog = LicenceDialog("{{WikiConference India 2026 video permission}}")
    assert dialog.chosen() == LICENCES[0].template


# -- the date override -----------------------------------------------------


def test_the_date_is_a_calendar_not_a_text_box(qt_app):
    """Typing a date invites the wrong format; Commons wants ISO."""
    from vcut.gui.main_window import MainWindow

    screen = MainWindow().metadata_screen
    assert screen.date_field.calendarPopup()
    assert screen.date_field.displayFormat() == "yyyy-MM-dd"


def test_no_override_means_each_clip_keeps_its_own_date(qt_app):
    from vcut.gui.main_window import MainWindow

    window = MainWindow()
    screen = window.metadata_screen

    screen.date_override_box.setChecked(False)
    assert window.state.settings.date_override == ""
    assert not screen.date_field.isEnabled()


def test_turning_the_override_on_stores_the_chosen_date(qt_app):
    from vcut.gui.main_window import MainWindow

    window = MainWindow()
    screen = window.metadata_screen

    screen.date_override_box.setChecked(True)
    assert screen.date_field.isEnabled()
    stored = window.state.settings.date_override
    assert stored == screen.date_field.date().toString("yyyy-MM-dd")
    # Commons wants ISO, which is what a calendar guarantees.
    assert len(stored) == 10 and stored[4] == "-"


def test_turning_it_off_again_clears_it(qt_app):
    # QDateEdit always shows a date, so the checkbox is what decides.
    from vcut.gui.main_window import MainWindow

    window = MainWindow()
    screen = window.metadata_screen

    screen.date_override_box.setChecked(True)
    assert window.state.settings.date_override
    screen.date_override_box.setChecked(False)
    assert window.state.settings.date_override == ""
