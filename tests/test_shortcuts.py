"""Keyboard shortcuts."""

import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QKeySequence  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from vcut.gui.shortcuts import GROUPS, SHORTCUTS, by_group, conflicts  # noqa: E402


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


def test_no_two_actions_claim_the_same_key():
    # A duplicate binding is a bug the user only finds by pressing the key.
    assert conflicts() == []


def test_every_shortcut_is_described():
    for shortcut in SHORTCUTS:
        assert shortcut.action
        assert shortcut.description
        assert shortcut.keys


def test_every_shortcut_belongs_to_a_known_group():
    for shortcut in SHORTCUTS:
        assert shortcut.group in GROUPS


def test_the_usual_video_editor_keys_are_present():
    # The bindings people arrive with from other editors.
    bound = {key for shortcut in SHORTCUTS for key in shortcut.keys}
    for key in ("Space", "J", "K", "L", "I", "O", ",", "."):
        assert key in bound, key


def test_play_and_pause_is_on_space_and_k():
    play = next(s for s in SHORTCUTS if s.action == "Play or pause")
    assert "Space" in play.keys
    assert "K" in play.keys


def test_marking_uses_i_and_o():
    marks = {s.action: s.keys for s in SHORTCUTS if s.group == "Marking clips"}
    assert marks["Set the start here"] == ("I",)
    assert marks["Set the end here"] == ("O",)


def test_every_key_sequence_is_one_qt_understands():
    for shortcut in SHORTCUTS:
        for key in shortcut.keys:
            assert not QKeySequence(key).isEmpty(), f"{shortcut.action}: {key}"


def test_the_groups_are_ordered_for_reading():
    # Playback first: it is what someone verifying cuts uses constantly.
    assert list(by_group())[0] == "Playback"


def test_shortcuts_with_a_slot_name_a_screen():
    for shortcut in SHORTCUTS:
        if shortcut.slot and shortcut.target:
            assert shortcut.target in ("setup", "verify", "metadata", "upload")


def test_every_slot_exists_on_its_screen(qt_app):
    from vcut.gui.screen_metadata import MetadataScreen
    from vcut.gui.screen_setup import SetupScreen
    from vcut.gui.screen_upload import UploadScreen
    from vcut.gui.screen_verify import VerifyScreen

    screens = {
        "setup": SetupScreen, "verify": VerifyScreen,
        "metadata": MetadataScreen, "upload": UploadScreen,
    }
    for shortcut in SHORTCUTS:
        if not (shortcut.slot and shortcut.target):
            continue
        screen = screens[shortcut.target]
        assert hasattr(screen, shortcut.slot), (
            f"{shortcut.action} calls {shortcut.target}.{shortcut.slot}, "
            f"which does not exist"
        )


def test_keys_are_spelled_for_a_reader():
    arrows = next(s for s in SHORTCUTS if s.action == "Back one frame")
    assert "←" in arrows.display()
    assert "or" in arrows.display()


# -- the help window -------------------------------------------------------


def test_the_window_lists_every_shortcut(qt_app):
    from vcut.gui.shortcuts_dialog import ShortcutsDialog

    dialog = ShortcutsDialog()
    assert str(len(SHORTCUTS)) in dialog.count.text()


def test_searching_narrows_the_list(qt_app):
    from vcut.gui.shortcuts_dialog import ShortcutsDialog

    dialog = ShortcutsDialog()
    dialog.search.setText("zoom")
    assert "of" in dialog.count.text()
    shown = sum(1 for name, _keys, _h in dialog._rows if not name.isHidden())
    assert 0 < shown < len(SHORTCUTS)


def test_searching_for_nothing_shows_everything_again(qt_app):
    from vcut.gui.shortcuts_dialog import ShortcutsDialog

    dialog = ShortcutsDialog()
    dialog.search.setText("zoom")
    dialog.search.setText("")
    assert dialog.count.text() == f"{len(SHORTCUTS)} shortcuts"


def test_a_search_matching_nothing_hides_every_group(qt_app):
    from vcut.gui.shortcuts_dialog import ShortcutsDialog

    dialog = ShortcutsDialog()
    dialog.search.setText("nothing matches this")
    assert "0 of" in dialog.count.text()
    for chrome, _indices in dialog._groups:
        assert all(widget.isHidden() for widget in chrome)
