"""Shared behaviour for the clip tables."""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtWidgets import QLineEdit, QStyledItemDelegate


class CellEditorDelegate(QStyledItemDelegate):
    """Keeps an inline editor inside its cell, and inside the view.

    Qt sizes a cell editor to the text it holds, which pushes the editor for
    a long title outside the viewport entirely — on the bottom row it ends up
    drawn over the buttons below, where it cannot be read or reached.
    """

    def createEditor(self, parent, option, index):  # noqa: N802
        editor = QLineEdit(parent)
        editor.setFrame(True)
        # Long titles scroll within the editor rather than widening it.
        editor.setMinimumWidth(0)
        # The app stylesheet gives line edits generous padding, which makes a
        # cell editor taller than the row it belongs to. Inside a table it
        # should match the row instead.
        editor.setStyleSheet("QLineEdit { padding: 1px 4px; min-height: 0; }")
        return editor

    def updateEditorGeometry(self, editor, option, index):  # noqa: N802
        # Match the cell exactly, rather than whatever height the editor's
        # own styling asks for.
        rect = QRect(option.rect)

        view = self.parent()
        viewport = getattr(view, "viewport", None)
        if callable(viewport):
            bounds = viewport().rect()
            # Never let the editor start or end outside the visible area.
            if rect.right() > bounds.right():
                rect.setRight(bounds.right())
            if rect.left() < bounds.left():
                rect.setLeft(bounds.left())
            if rect.bottom() > bounds.bottom():
                rect.moveBottom(bounds.bottom())
            if rect.top() < bounds.top():
                rect.moveTop(bounds.top())
            # A partly scrolled row can still be shorter than the editor.
            if rect.height() > bounds.height():
                rect.setHeight(bounds.height())

        editor.setGeometry(rect)


def configure_table(table) -> None:
    """Apply the shared editing and scrolling behaviour."""
    table.setItemDelegate(CellEditorDelegate(table))
    # Scrolling by pixel keeps a partly visible bottom row from jumping when
    # it is clicked into.
    table.setVerticalScrollMode(table.ScrollMode.ScrollPerPixel)
    table.setHorizontalScrollMode(table.ScrollMode.ScrollPerPixel)
    table.setWordWrap(False)
    table.setTextElideMode(Qt.ElideRight)
