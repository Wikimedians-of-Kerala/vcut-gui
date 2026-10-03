"""Column behaviour on the clip tables.

A Stretch or ResizeToContents section cannot be dragged at all, which is the
bug these guard against: the dividers looked inert because they were.
"""

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QHeaderView  # noqa: E402

from vcut.gui.state import AppState  # noqa: E402
from vcut.gui.theme import Theme, apply_theme, stylesheet  # noqa: E402
from vcut.settings import AppSettings  # noqa: E402


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    apply_theme(Theme.DARK)
    yield app


@pytest.fixture
def screens(qt_app):
    from vcut.gui.screen_metadata import MetadataScreen
    from vcut.gui.screen_upload import UploadScreen
    from vcut.gui.screen_verify import VerifyScreen

    state = AppState(AppSettings())
    return {
        "verify": VerifyScreen(state),
        "metadata": MetadataScreen(state),
        "upload": UploadScreen(state),
    }


def test_every_column_can_be_resized_by_hand(screens):
    for name, screen in screens.items():
        header = screen.table.horizontalHeader()
        modes = [
            header.sectionResizeMode(column)
            for column in range(screen.table.columnCount())
        ]
        assert all(mode == QHeaderView.Interactive for mode in modes), name


def test_resizing_a_column_sticks(screens):
    table = screens["verify"].table
    table.horizontalHeader().resizeSection(1, 420)
    assert table.columnWidth(1) == 420


def test_columns_can_be_reordered(screens):
    for name, screen in screens.items():
        assert screen.table.horizontalHeader().sectionsMovable(), name


def test_columns_start_at_a_usable_width(screens):
    table = screens["verify"].table
    # The programme title is what identifies a row.
    assert table.columnWidth(1) >= 200


def test_a_column_cannot_be_dragged_away_to_nothing(screens):
    for name, screen in screens.items():
        assert screen.table.horizontalHeader().minimumSectionSize() >= 20, name


def test_the_header_divider_is_drawn_as_a_grip(qt_app):
    sheet = stylesheet(Theme.DARK)
    assert "QHeaderView::section:horizontal" in sheet
    assert "double" in sheet


# -- inline editing --------------------------------------------------------


def test_cells_use_the_containing_delegate(screens):
    from vcut.gui.table_support import CellEditorDelegate

    for name, screen in screens.items():
        assert isinstance(screen.table.itemDelegate(), CellEditorDelegate), name


def test_an_editor_stays_inside_the_view(qt_app, screens):
    from PySide6.QtWidgets import QLineEdit

    from vcut.models import Clip

    screen = screens["verify"]
    screen.state.set_clips([
        Clip(programme=f"A very long session title number {i} " * 2,
             start_time=f"00:{i:02d}:00", end_time=f"00:{i:02d}:30")
        for i in range(20)
    ])
    table = screen.table
    table.resize(500, 200)
    table.show()
    qt_app.processEvents()

    last = table.rowCount() - 1
    table.setCurrentCell(last, 1)
    table.scrollToBottom()
    qt_app.processEvents()
    table.editItem(table.item(last, 1))
    qt_app.processEvents()

    editors = table.viewport().findChildren(QLineEdit)
    assert editors, "no editor was created"
    geometry = editors[0].geometry()
    bounds = table.viewport().rect()
    # The bug this guards: the editor for the bottom row was drawn past the
    # viewport, over the buttons below, where it could not be used.
    assert geometry.right() <= bounds.right() + 1
    assert geometry.bottom() <= bounds.bottom() + 1


def test_the_editor_matches_the_row_height(qt_app, screens):
    from PySide6.QtWidgets import QLineEdit

    from vcut.models import Clip

    screen = screens["verify"]
    screen.state.set_clips([Clip(programme="A", start_time="0:10", end_time="0:20")])
    table = screen.table
    table.show()
    qt_app.processEvents()
    table.setCurrentCell(0, 1)
    table.editItem(table.item(0, 1))
    qt_app.processEvents()

    editors = table.viewport().findChildren(QLineEdit)
    assert editors
    # Generous app-wide padding must not inflate a cell editor.
    assert editors[0].height() <= table.rowHeight(0) + 4
