"""The Settings window."""

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from vcut.settings import AppSettings  # noqa: E402


@pytest.fixture(scope="module")
def qt_app():
    yield QApplication.instance() or QApplication([])


def test_it_is_reachable_from_the_menu(qt_app):
    """Settings with no way to open them are settings nobody changes."""
    from vcut.gui.main_window import MainWindow

    window = MainWindow()
    file_menu = next(
        action.menu()
        for action in window.menuBar().actions()
        if action.text() == "&File"
    )
    names = [a.text() for a in file_menu.actions() if not a.isSeparator()]
    assert any("Settings" in name and "FFmpeg" not in name for name in names)


def test_video_information_is_a_view_action(qt_app):
    # It opens nothing and changes nothing, so it does not belong in File.
    from vcut.gui.main_window import MainWindow

    window = MainWindow()
    menus = {
        action.text(): [
            a.text() for a in action.menu().actions() if not a.isSeparator()
        ]
        for action in window.menuBar().actions()
        if action.menu()
    }
    assert any("Video information" in n for n in menus["&View"])
    assert not any("Video information" in n for n in menus["&File"])


def test_the_naming_options_are_shown(qt_app):
    from vcut.gui.settings_dialog import SettingsDialog

    settings = AppSettings()
    settings.commons_include_code = False
    settings.commons_word_separator = "_"

    dialog = SettingsDialog(settings)
    assert dialog.include_code.isChecked() is False
    assert dialog.separator.currentData() == "_"


def test_accepting_stores_what_was_chosen(qt_app, tmp_path, monkeypatch):
    from vcut.gui.settings_dialog import SettingsDialog

    settings = AppSettings()
    monkeypatch.setattr(type(settings), "save", lambda self: None)

    dialog = SettingsDialog(settings)
    dialog.include_code.setChecked(False)
    dialog.separator.setCurrentIndex(dialog.separator.findData("-"))
    dialog.max_length.setValue(60)
    dialog.ascii_only.setChecked(True)
    dialog._accept()

    assert settings.commons_include_code is False
    assert settings.commons_word_separator == "-"
    assert settings.slug_max_length == 60
    assert settings.ascii_filenames is True


def test_an_emptied_pattern_falls_back(qt_app, monkeypatch):
    # A blank template would name every file ".webm".
    from vcut.gui.settings_dialog import SettingsDialog

    settings = AppSettings()
    monkeypatch.setattr(type(settings), "save", lambda self: None)

    dialog = SettingsDialog(settings)
    dialog.commons_template.setText("   ")
    dialog.disk_template.setText("")
    dialog._accept()

    assert settings.commons_filename_template
    assert settings.filename_template


def test_cancelling_changes_nothing(qt_app):
    from vcut.gui.settings_dialog import SettingsDialog

    settings = AppSettings()
    before = settings.commons_word_separator

    dialog = SettingsDialog(settings)
    dialog.separator.setCurrentIndex(dialog.separator.findData("_"))
    dialog.reject()

    assert settings.commons_word_separator == before
