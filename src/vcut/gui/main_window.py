"""The main window: four screens, a step bar, and a log."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from ..settings import AppSettings
from .resources import app_icon, logo_pixmap
from .screen_metadata import MetadataScreen
from .screen_setup import SetupScreen
from .screen_upload import UploadScreen
from .screen_verify import VerifyScreen
from .state import AppState

STEPS = (
    ("1. Set up", "Choose the video, the timecodes and how to encode"),
    ("2. Verify and split", "Check each cut point, then split the video"),
    ("3. Metadata", "Fetch session details and write Commons descriptions"),
    ("4. Upload", "Send the finished files to Wikimedia Commons"),
)


class StepBar(QWidget):
    """The four step buttons across the top."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)

        logo = logo_pixmap(28)
        if not logo.isNull():
            badge = QLabel()
            badge.setPixmap(logo)
            badge.setToolTip("vcut")
            layout.addWidget(badge)
            layout.addSpacing(8)

        self.buttons: list[QPushButton] = []
        for title, tooltip in STEPS:
            button = QPushButton(title)
            button.setCheckable(True)
            button.setAutoDefault(False)
            button.setToolTip(tooltip)
            button.setCursor(Qt.PointingHandCursor)
            layout.addWidget(button)
            self.buttons.append(button)
        layout.addStretch(1)

    def set_current(self, index: int) -> None:
        for position, button in enumerate(self.buttons):
            button.setChecked(position == index)


class MainWindow(QMainWindow):
    def __init__(self, settings: AppSettings | None = None) -> None:
        super().__init__()
        self.setWindowTitle("vcut — conference video cutter")
        self.setWindowIcon(app_icon())
        self.resize(1180, 780)

        self.state = AppState(settings)
        self.state.log_message.connect(self._append_log)

        self.steps = StepBar()
        self.stack = QStackedWidget()

        self.setup_screen = SetupScreen(self.state)
        self.verify_screen = VerifyScreen(self.state)
        self.metadata_screen = MetadataScreen(self.state)
        self.upload_screen = UploadScreen(self.state)

        for screen in (self.setup_screen, self.verify_screen,
                       self.metadata_screen, self.upload_screen):
            self.stack.addWidget(screen)

        for index, button in enumerate(self.steps.buttons):
            button.clicked.connect(lambda _=False, i=index: self.go_to(i))

        self.hint = QLabel(STEPS[0][1])
        self.hint.setStyleSheet("color: gray; padding: 0 12px 6px 12px;")

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.steps)
        layout.addWidget(self.hint)
        layout.addWidget(self.stack, 1)
        layout.addWidget(self._navigation())
        self.setCentralWidget(central)

        self._build_log_dock()
        self._build_menu()
        self.setStatusBar(QStatusBar())

        self.verify_screen.finished_cutting.connect(self._cutting_finished)
        self.metadata_screen.files_ready.connect(self._refresh_upload)

        self.go_to(0)

    def _navigation(self) -> QWidget:
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 6, 12, 12)

        self.back_button = QPushButton("← Back")
        self.back_button.setAutoDefault(False)
        self.back_button.clicked.connect(lambda: self.go_to(self.stack.currentIndex() - 1))
        layout.addWidget(self.back_button)
        layout.addStretch(1)

        self.next_button = QPushButton("Next →")
        self.next_button.setAutoDefault(False)
        self.next_button.clicked.connect(lambda: self.go_to(self.stack.currentIndex() + 1))
        layout.addWidget(self.next_button)
        return bar

    def _build_log_dock(self) -> None:
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(5000)
        self.log_view.setPlaceholderText("FFmpeg output appears here.")

        self.log_dock = QDockWidget("Log", self)
        self.log_dock.setWidget(self.log_view)
        self.log_dock.setObjectName("log-dock")
        self.addDockWidget(Qt.BottomDockWidgetArea, self.log_dock)
        self.log_dock.hide()

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")

        save_action = QAction("&Save settings", self)
        save_action.setShortcut(QKeySequence.Save)
        save_action.triggered.connect(self._save_settings)
        file_menu.addAction(save_action)

        file_menu.addSeparator()
        quit_action = QAction("&Quit", self)
        quit_action.setShortcut(QKeySequence.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        view_menu = self.menuBar().addMenu("&View")
        log_action = self.log_dock.toggleViewAction()
        log_action.setText("Show &log")
        view_menu.addAction(log_action)

        help_menu = self.menuBar().addMenu("&Help")
        about_action = QAction("&About", self)
        about_action.triggered.connect(self._about)
        help_menu.addAction(about_action)

    # -- navigation --------------------------------------------------------

    def go_to(self, index: int) -> None:
        index = max(0, min(index, self.stack.count() - 1))

        # Entering a later screen needs the settings from the setup form.
        if index > 0:
            self.setup_screen.apply_to_settings()
        if index == 2:
            self.metadata_screen.refresh()
        if index == 3:
            self._refresh_upload()

        self.stack.setCurrentIndex(index)
        self.steps.set_current(index)
        self.hint.setText(STEPS[index][1])
        self.back_button.setEnabled(index > 0)
        self.next_button.setEnabled(index < self.stack.count() - 1)

    def _cutting_finished(self) -> None:
        self.statusBar().showMessage("Cutting finished.", 5000)
        self.metadata_screen.refresh()

    def _refresh_upload(self) -> None:
        self.metadata_screen.refresh()
        self.upload_screen.set_files(self.metadata_screen.prepared_files())
        self.upload_screen.check_login()

    def _append_log(self, message: str) -> None:
        self.log_view.appendPlainText(message)

    def _save_settings(self) -> None:
        self.setup_screen.apply_to_settings()
        self.statusBar().showMessage("Settings saved.", 3000)

    def _about(self) -> None:
        from .. import __version__

        box = QMessageBox(self)
        box.setWindowTitle("About vcut")
        box.setTextFormat(Qt.RichText)
        box.setText(
            f"<b>vcut {__version__}</b><br><br>"
            "Cuts conference recordings into per-session clips, fetches each "
            "session's details from an Eventyay/pretalx schedule, and prepares "
            "them for Wikimedia Commons.<br><br>"
            "Licensed under the GNU GPL v3 or later."
        )
        pixmap = logo_pixmap(96)
        if not pixmap.isNull():
            box.setIconPixmap(pixmap)
        box.exec()

    def closeEvent(self, event) -> None:  # noqa: N802
        try:
            self.setup_screen.apply_to_settings()
        except Exception:  # noqa: BLE001 - never block closing
            pass
        super().closeEvent(event)
