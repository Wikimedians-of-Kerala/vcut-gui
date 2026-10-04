"""The main window: four screens, a step bar, and a log."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
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

from pathlib import Path

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

        # The step's description lives here rather than in a banner of its
        # own: a separate heading row repeated what the bar already said and
        # cost every screen a line of height.
        self.caption = QLabel("")
        self.caption.setObjectName("screenSubheading")
        self.caption.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self.caption)

    def set_current(self, index: int) -> None:
        """Mark one step current, and everything before it as done."""
        self.caption.setText(
            f"{STEPS[index][1]}   ·   Step {index + 1} of {len(STEPS)}"
        )
        for position, button in enumerate(self.buttons):
            button.setChecked(position == index)
            button.setProperty("current", position == index)
            button.setProperty("done", position < index)
            # Qt only re-reads a dynamic property after the style is refreshed.
            button.style().unpolish(button)
            button.style().polish(button)


class MainWindow(QMainWindow):
    def __init__(self, settings: AppSettings | None = None) -> None:
        super().__init__()
        self.setWindowTitle("vcut — conference video cutter")
        self.setWindowIcon(app_icon())
        self.resize(1180, 780)

        self.state = AppState(settings)
        self.state.log_message.connect(self._append_log)
        self.state.source_changed.connect(self._source_changed)

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

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.steps)
        layout.addWidget(self.stack, 1)
        layout.addWidget(self._navigation())
        self.setCentralWidget(central)

        # Each screen contributes its actions to the shared bottom row.
        for screen in (self.setup_screen, self.verify_screen,
                       self.metadata_screen, self.upload_screen):
            actions = getattr(screen, "action_widgets", None)
            self.action_slot.addWidget(actions() if callable(actions) else QWidget())

        self._build_log_dock()
        self._build_menu()
        self.setStatusBar(QStatusBar())

        self.verify_screen.finished_cutting.connect(self._cutting_finished)
        self.metadata_screen.files_ready.connect(self._refresh_upload)

        self.go_to(0)

    def _navigation(self) -> QWidget:
        """The single bottom row: Back, the screen's own actions, then Next.

        Each screen used to carry its own action row above this one, leaving
        two mostly-empty full-width strips at the foot of every page. Screens
        now hand their buttons here instead.
        """
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 6, 12, 10)
        layout.setSpacing(8)

        self.back_button = QPushButton("Back")
        self.back_button.setAutoDefault(False)
        icons.apply(self.back_button, "back")
        self.back_button.clicked.connect(lambda: self.go_to(self.stack.currentIndex() - 1))
        layout.addWidget(self.back_button)

        # Each screen's own actions are slotted in here when it is shown.
        self.action_slot = QStackedWidget()
        layout.addWidget(self.action_slot, 1)

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

        new_action = QAction("&New project", self)
        new_action.setShortcut(QKeySequence.New)
        new_action.triggered.connect(self._new_project)
        file_menu.addAction(new_action)

        open_action = QAction("&Open project…", self)
        open_action.setShortcut(QKeySequence.Open)
        open_action.triggered.connect(self._open_project)
        file_menu.addAction(open_action)

        self.save_project_action = QAction("&Save project", self)
        self.save_project_action.setShortcut(QKeySequence.Save)
        self.save_project_action.triggered.connect(self._save_project)
        file_menu.addAction(self.save_project_action)

        save_as_action = QAction("Save project &as…", self)
        save_as_action.setShortcut(QKeySequence.SaveAs)
        save_as_action.triggered.connect(lambda: self._save_project(ask=True))
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()

        login_action = QAction("Sign in to &Commons…", self)
        login_action.triggered.connect(self._show_login)
        file_menu.addAction(login_action)

        ffmpeg_action = QAction("&FFmpeg settings…", self)
        ffmpeg_action.triggered.connect(self._show_ffmpeg_settings)
        file_menu.addAction(ffmpeg_action)

        save_action = QAction("Save se&ttings", self)
        save_action.triggered.connect(self._save_settings)
        file_menu.addAction(save_action)

        file_menu.addSeparator()
        quit_action = QAction("&Quit", self)
        quit_action.setShortcut(QKeySequence.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        self.info_action = QAction("&Video information…", self)
        self.info_action.setShortcut("Ctrl+I")
        self.info_action.setEnabled(False)
        self.info_action.triggered.connect(self._show_media_info)
        file_menu.insertAction(save_action, self.info_action)
        file_menu.insertSeparator(save_action)

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
        self.action_slot.setCurrentIndex(index)
        self.steps.set_current(index)
        self.back_button.setEnabled(index > 0)
        self.next_button.setEnabled(index < self.stack.count() - 1)

    def _source_changed(self, path: str) -> None:
        self.info_action.setEnabled(bool(path))

    def _cutting_finished(self) -> None:
        self.statusBar().showMessage("Cutting finished.", 5000)
        self.metadata_screen.refresh()

    def _refresh_upload(self) -> None:
        self.metadata_screen.refresh()
        self.upload_screen.set_files(self.metadata_screen.prepared_files())
        self.upload_screen.check_login()

    # -- projects ----------------------------------------------------------

    def _new_project(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        if self.state.clips:
            answer = QMessageBox.question(
                self, "Start a new project",
                "Clear the current clips and start again?\n\n"
                "Anything unsaved will be lost.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        self.state.project_path = ""
        self.state.set_clips([])
        self.state.set_source("", None)
        self._update_title()
        self.statusBar().showMessage("New project.", 3000)

    def _open_project(self) -> None:
        from PySide6.QtWidgets import QFileDialog, QMessageBox

        from ..project import PROJECT_SUFFIX, Project, ProjectError

        path, _ = QFileDialog.getOpenFileName(
            self, "Open a project", "",
            f"vcut projects (*{PROJECT_SUFFIX});;All files (*)",
        )
        if not path:
            return
        try:
            project = Project.load(path)
        except ProjectError as exc:
            QMessageBox.critical(self, "Could not open", str(exc))
            return

        self.state.load_project(project)
        self.setup_screen.adopt_project(project)
        self.verify_screen.set_verified_rows(project.verified)
        self._update_title()
        self.statusBar().showMessage(
            f"Opened {Path(path).name} — {project.summary()}.", 6000
        )

    def _save_project(self, *, ask: bool = False) -> None:
        from PySide6.QtWidgets import QFileDialog, QMessageBox

        from ..project import PROJECT_SUFFIX

        path = self.state.project_path
        if ask or not path:
            suggested = path or self._suggested_project_name()
            path, _ = QFileDialog.getSaveFileName(
                self, "Save the project", suggested,
                f"vcut projects (*{PROJECT_SUFFIX});;All files (*)",
            )
            if not path:
                return

        self.setup_screen.apply_to_settings()
        project = self.state.to_project()
        project.verified = set(self.verify_screen.verified_rows())
        try:
            written = project.save(path)
        except OSError as exc:
            QMessageBox.critical(self, "Could not save", str(exc))
            return

        self.state.project_path = str(written)
        self._update_title()
        self.statusBar().showMessage(f"Saved {written.name}.", 4000)

    def _suggested_project_name(self) -> str:
        if self.state.source_path:
            return str(Path(self.state.source_path).with_suffix(".vcut"))
        return "project.vcut"

    def _update_title(self) -> None:
        name = Path(self.state.project_path).stem if self.state.project_path else ""
        self.setWindowTitle(
            f"{name} — vcut" if name else "vcut — conference video cutter"
        )

    def _show_login(self) -> None:
        from .login_dialog import LoginDialog

        dialog = LoginDialog(self)
        dialog.logged_in.connect(lambda _u: self.upload_screen.check_login())
        dialog.exec()

    def _show_ffmpeg_settings(self) -> None:
        from .ffmpeg_dialog import FFmpegDialog

        dialog = FFmpegDialog(self.state.settings, self)
        dialog.settings_changed.connect(self.setup_screen.reload_encoding)
        dialog.exec()

    def _show_media_info(self) -> None:
        from .media_info_dialog import MediaInfoDialog

        MediaInfoDialog(self.state.source_path, self.state.media_info, self).exec()

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
        # Walking from the window covers everything, including the screens'
        # action rows: those are reparented into the shared bottom bar, so a
        # screen can no longer find them among its own children and they kept
        # the previous theme's colour.
        icons.restyle_widget(self)
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
