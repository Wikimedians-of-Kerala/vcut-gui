"""The main window: four screens, a step bar, and a log."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QDockWidget,
    QFrame,
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
from . import icons
from .resources import app_icon, logo_pixmap
from .screen_metadata import MetadataScreen
from .screen_setup import SetupScreen
from .screen_upload import UploadScreen
from .screen_verify import VerifyScreen
from .state import AppState
from .theme import Theme, apply_theme

STEPS = (
    ("Set up", "Choose the video, the timecodes and how to encode"),
    ("Verify and split", "Check each cut point, then split the video"),
    ("Metadata", "Fetch session details and write Commons descriptions"),
    ("Upload", "Send the finished files to Wikimedia Commons"),
)


class StepBar(QWidget):
    """The four steps across the top, with the current one filled in."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 8)
        layout.setSpacing(2)

        logo = logo_pixmap(26)
        if not logo.isNull():
            badge = QLabel()
            badge.setPixmap(logo)
            badge.setToolTip("vcut")
            layout.addWidget(badge)
            layout.addSpacing(12)

        self.buttons: list[QPushButton] = []
        self.separators: list[QLabel] = []
        for index, (title, tooltip) in enumerate(STEPS):
            button = QPushButton(f"{index + 1}.  {title}")
            button.setObjectName("stepButton")
            button.setCheckable(True)
            button.setAutoDefault(False)
            button.setToolTip(tooltip)
            button.setCursor(Qt.PointingHandCursor)
            layout.addWidget(button)
            self.buttons.append(button)

            if index < len(STEPS) - 1:
                chevron = QLabel("›")
                chevron.setObjectName("screenSubheading")
                chevron.setAlignment(Qt.AlignCenter)
                layout.addWidget(chevron)
                self.separators.append(chevron)

        layout.addStretch(1)

    def set_current(self, index: int) -> None:
        """Mark one step current, and everything before it as done."""
        for position, button in enumerate(self.buttons):
            button.setChecked(position == index)
            button.setProperty("current", position == index)
            button.setProperty("done", position < index)
            # Qt only re-reads a dynamic property after the style is refreshed.
            button.style().unpolish(button)
            button.style().polish(button)


class ScreenHeading(QWidget):
    """The banner at the top of each screen, naming the step you are on."""

    def __init__(self, step: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        title, subtitle = STEPS[step]

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 10, 14, 8)

        panel = QFrame()
        panel.setObjectName("screenHeadingPanel")
        panel.setAttribute(Qt.WA_StyledBackground, True)

        row = QHBoxLayout(panel)
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(14)

        number = QLabel(str(step + 1))
        number.setObjectName("screenStepNumber")
        number.setAlignment(Qt.AlignCenter)
        row.addWidget(number)

        text = QVBoxLayout()
        text.setSpacing(1)
        heading = QLabel(title)
        heading.setObjectName("screenHeading")
        text.addWidget(heading)

        caption = QLabel(subtitle)
        caption.setObjectName("screenSubheading")
        caption.setWordWrap(True)
        text.addWidget(caption)
        row.addLayout(text, 1)

        progress = QLabel(f"Step {step + 1} of {len(STEPS)}")
        progress.setObjectName("screenSubheading")
        progress.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row.addWidget(progress)

        outer.addWidget(panel)


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

        for step, screen in enumerate((self.setup_screen, self.verify_screen,
                                       self.metadata_screen, self.upload_screen)):
            page = QWidget()
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(0, 0, 0, 0)
            page_layout.setSpacing(0)
            page_layout.addWidget(ScreenHeading(step))
            page_layout.addWidget(screen, 1)
            self.stack.addWidget(page)

        for index, button in enumerate(self.steps.buttons):
            button.clicked.connect(lambda _=False, i=index: self.go_to(i))

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.steps)
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

        self.back_button = QPushButton("Back")
        self.back_button.setAutoDefault(False)
        icons.apply(self.back_button, "back")
        self.back_button.clicked.connect(lambda: self.go_to(self.stack.currentIndex() - 1))
        layout.addWidget(self.back_button)
        layout.addStretch(1)

        self.next_button = QPushButton("Next")
        self.next_button.setAutoDefault(False)
        icons.apply(self.next_button, "next")
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

        view_menu.addSeparator()
        theme_menu = view_menu.addMenu("&Theme")
        group = QActionGroup(self)
        group.setExclusive(True)
        try:
            current = Theme(self.state.settings.theme)
        except ValueError:
            current = Theme.SYSTEM
        for theme in Theme:
            action = QAction(theme.label, self, checkable=True)
            action.setChecked(theme is current)
            action.triggered.connect(lambda _=False, t=theme: self._set_theme(t))
            group.addAction(action)
            theme_menu.addAction(action)

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
        self.back_button.setEnabled(index > 0)
        self.next_button.setEnabled(index < self.stack.count() - 1)

    def _cutting_finished(self) -> None:
        self.statusBar().showMessage("Cutting finished.", 5000)
        self.metadata_screen.refresh()

    def _refresh_upload(self) -> None:
        self.metadata_screen.refresh()
        self.upload_screen.set_files(self.metadata_screen.prepared_files())
        self.upload_screen.check_login()

    def _set_theme(self, theme: Theme) -> None:
        """Switch theme and repaint everything that caches its own colours."""
        apply_theme(theme)
        self.state.settings.theme = theme.value
        self.state.save_settings()
        self.refresh_theme()
        self.statusBar().showMessage(f"Theme: {theme.label}.", 3000)

    def refresh_theme(self) -> None:
        """Rebuild colours and icons that are not taken from the palette."""
        self.setWindowIcon(app_icon())
        for screen in (self.setup_screen, self.verify_screen,
                       self.metadata_screen, self.upload_screen):
            restyle = getattr(screen, "restyle", None)
            if callable(restyle):
                restyle()

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
