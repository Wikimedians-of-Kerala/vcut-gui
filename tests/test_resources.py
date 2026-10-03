"""The bundled logo and the icon built from it."""

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from vcut.gui.resources import ICON_SIZES, LOGO_FILE, app_icon, logo_path, logo_pixmap  # noqa: E402


@pytest.fixture(scope="module")
def qt_app():
    # QPixmap needs an application instance before it can be constructed.
    app = QApplication.instance() or QApplication([])
    yield app


def test_the_logo_ships_with_the_package():
    assert LOGO_FILE.is_file()
    assert logo_path().endswith(".svg")


def test_the_icon_is_rendered_at_every_listed_size(qt_app):
    sizes = {size.width() for size in app_icon().availableSizes()}
    assert sizes == set(ICON_SIZES)


def test_the_icon_keeps_its_transparency(qt_app):
    # A square pixmap around a non-square logo must not paint in a background.
    assert app_icon().pixmap(64, 64).hasAlphaChannel()


def test_the_icon_is_square_at_each_size(qt_app):
    for size in app_icon().availableSizes():
        assert size.width() == size.height()


def test_the_about_pixmap_is_the_size_asked_for(qt_app):
    assert logo_pixmap(96).size().width() == 96


def test_a_missing_logo_gives_an_empty_icon(qt_app, monkeypatch):
    import vcut.gui.resources as resources

    monkeypatch.setattr(resources, "logo_path", lambda: "")
    assert resources.app_icon().isNull()
    assert resources.logo_pixmap().isNull()
