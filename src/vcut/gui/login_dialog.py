"""Signing in to Wikimedia Commons, without a terminal.

Pywikibot normally wants a hand-written configuration file and a shell
session to log in. This window does that for the user: they paste the two
values Special:BotPasswords gave them, press Sign in, and the app writes the
configuration and stores the secret in the system keychain.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QTabWidget,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import auth
from . import icons
from .widgets import StatusLabel, space_form
from .workers import start


class _LoginSignals(QObject):
    finished = Signal(object)


class _LoginWorker(QRunnable):
    """Verify credentials off the GUI thread."""

    def __init__(self, credentials: auth.Credentials) -> None:
        super().__init__()
        self.signals = _LoginSignals()
        self._credentials = credentials

    def run(self) -> None:
        try:
            result = auth.verify(self._credentials)
        except Exception as exc:  # noqa: BLE001 - surfaced in the window
            result = auth.LoginResult(message=str(exc))
        self.signals.finished.emit(result)


class LoginDialog(QDialog):
    """Collect a bot password, check it, and remember it."""

    logged_in = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Sign in to Wikimedia Commons")
        self.resize(560, 480)
        self._busy = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        outer.addWidget(self.tabs)

        password_page = QWidget()
        layout = QVBoxLayout(password_page)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(12)
        self.tabs.addTab(password_page, "Bot password")

        intro = QLabel(
            "Uploading needs a <b>bot password</b> — a separate, revocable "
            "password for this app. It is not your account password, and you "
            "can cancel it at any time without changing your login."
        )
        intro.setWordWrap(True)
        intro.setTextFormat(Qt.RichText)
        layout.addWidget(intro)

        steps = QLabel(
            "1. Open Special:BotPasswords and create one named <i>vcut</i>.<br>"
            "2. Tick <i>Upload new files</i> and <i>Edit existing pages</i>.<br>"
            "3. Copy the username and the generated password here."
        )
        steps.setWordWrap(True)
        steps.setTextFormat(Qt.RichText)
        steps.setObjectName("screenSubheading")
        layout.addWidget(steps)

        open_page = QPushButton("Open Special:BotPasswords")
        open_page.setAutoDefault(False)
        icons.apply(open_page, "login")
        open_page.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(auth.BOT_PASSWORD_URL))
        )
        row = QHBoxLayout()
        row.addWidget(open_page)
        row.addStretch(1)
        layout.addLayout(row)

        group = QGroupBox("Your bot password")
        form = QFormLayout(group)
        space_form(form)

        self.username_field = QLineEdit()
        self.username_field.setPlaceholderText("YourName@vcut")
        self.username_field.textChanged.connect(self._validate)
        form.addRow("Username", self.username_field)

        self.password_field = QLineEdit()
        self.password_field.setEchoMode(QLineEdit.Password)
        self.password_field.setPlaceholderText("the long generated password")
        self.password_field.textChanged.connect(self._validate)
        form.addRow("Password", self.password_field)

        self.show_box = QCheckBox("Show the password")
        self.show_box.toggled.connect(
            lambda on: self.password_field.setEchoMode(
                QLineEdit.Normal if on else QLineEdit.Password
            )
        )
        form.addRow("", self.show_box)

        self.remember_box = QCheckBox("Remember it in this computer's keychain")
        self.remember_box.setChecked(True)
        form.addRow("", self.remember_box)
        layout.addWidget(group)

        self.status = StatusLabel("")
        layout.addWidget(self.status)
        layout.addStretch(1)

        buttons = QDialogButtonBox()
        self.sign_in = QPushButton("Sign in")
        self.sign_in.setDefault(True)
        icons.apply(self.sign_in, "login")
        self.sign_in.clicked.connect(self._sign_in)
        buttons.addButton(self.sign_in, QDialogButtonBox.AcceptRole)

        self.forget_button = QPushButton("Forget")
        self.forget_button.setAutoDefault(False)
        self.forget_button.setToolTip("Remove the stored password from this computer")
        icons.apply(self.forget_button, "remove")
        self.forget_button.clicked.connect(self._forget)
        buttons.addButton(self.forget_button, QDialogButtonBox.DestructiveRole)

        close = buttons.addButton(QDialogButtonBox.Close)
        close.setAutoDefault(False)
        close.clicked.connect(self.reject)
        layout.addWidget(buttons)

        self.tabs.addTab(self._browser_page(), "Sign in with a browser")

        self._load_existing()
        self._check_keychain()

    # -- browser login -----------------------------------------------------

    def _browser_page(self) -> QWidget:
        """The real Commons login page, for passkeys and two-factor."""
        from . import browser_login

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)

        note = QLabel(
            "Use this if your account has a <b>passkey</b> or two-factor "
            "sign-in. Those are answered by the wiki's own page — a passkey "
            "is tied to the browser and cannot be typed into an app — so "
            "Commons is shown here and the app picks up the session "
            "afterwards.<br><br>"
            "This signs you in for now. A bot password is better for working "
            "across several days, because a session expires."
        )
        note.setWordWrap(True)
        note.setTextFormat(Qt.RichText)
        layout.addWidget(note)

        if not browser_login.webengine_available():
            layout.addWidget(StatusLabel(
                "This build has no embedded browser, so signing in this way "
                "is unavailable. Use a bot password instead.", "warn"
            ))
            layout.addStretch(1)
            return page

        row = QHBoxLayout()
        open_browser = QPushButton("Open the Commons login page")
        open_browser.setAutoDefault(False)
        icons.apply(open_browser, "login")
        open_browser.clicked.connect(self._open_browser_login)
        row.addWidget(open_browser)

        self.browser_check = QPushButton("Check session")
        self.browser_check.setAutoDefault(False)
        icons.apply(self.browser_check, "refresh")
        self.browser_check.clicked.connect(self._check_browser_session)
        row.addWidget(self.browser_check)

        forget = QPushButton("Sign out")
        forget.setAutoDefault(False)
        icons.apply(forget, "remove")
        forget.clicked.connect(self._forget_browser_session)
        row.addWidget(forget)
        row.addStretch(1)
        layout.addLayout(row)

        self.browser_status = StatusLabel("")
        layout.addWidget(self.browser_status)
        layout.addStretch(1)
        self._refresh_browser_status()
        return page

    def _open_browser_login(self) -> None:
        from .browser_window import BrowserLoginWindow

        window = BrowserLoginWindow(self)
        window.signed_in.connect(self._browser_signed_in)
        window.exec()

    def _browser_signed_in(self, username: str) -> None:
        self.browser_status.show_message(
            f"Signed in as {username}. Uploading will use this session.", "good"
        )
        self.logged_in.emit(username)

    def _check_browser_session(self) -> None:
        from . import browser_login

        self.browser_status.show_message("Asking Commons…", "info")
        from PySide6.QtWidgets import QApplication

        QApplication.processEvents()

        session = browser_login.load_session()
        if session is None:
            self.browser_status.show_message("No browser session stored.", "muted")
            return
        name = browser_login.whoami(session)
        if not name:
            self.browser_status.show_message(
                "The stored session has expired — sign in again.", "warn"
            )
            return
        if browser_login.can_upload(session):
            self.browser_status.show_message(
                f"Signed in as {name}, and the session can upload.", "good"
            )
        else:
            self.browser_status.show_message(
                f"Signed in as {name}, but the session cannot upload.", "warn"
            )

    def _forget_browser_session(self) -> None:
        from . import browser_login

        browser_login.forget_session()
        self.browser_status.show_message("Browser session removed.", "muted")

    def _refresh_browser_status(self) -> None:
        from . import browser_login

        session = browser_login.load_session()
        if session is None:
            self.browser_status.show_message("Not signed in through a browser.", "muted")
        else:
            self.browser_status.show_message(
                f"A session for {session.username} is stored — press Check "
                f"session to confirm it still works.", "muted"
            )

    # -- state -------------------------------------------------------------

    def _load_existing(self) -> None:
        stored = auth.load()
        if stored is None:
            self.forget_button.setEnabled(False)
            return
        self.username_field.setText(stored.username)
        self.password_field.setText(stored.password)
        self.status.show_message(
            f"Signed in as {stored.account} on this computer.", "good"
        )

    def _check_keychain(self) -> None:
        if auth.keyring_available():
            return
        self.remember_box.setChecked(False)
        self.remember_box.setEnabled(False)
        self.remember_box.setText(
            "No keychain on this computer — the password cannot be remembered"
        )

    def _credentials(self) -> auth.Credentials:
        return auth.Credentials(
            username=self.username_field.text().strip(),
            password=self.password_field.text(),
        )

    def _validate(self) -> None:
        credentials = self._credentials()
        if not credentials.username and not credentials.password:
            self.status.show_message("")
            self.sign_in.setEnabled(False)
            return
        problems = credentials.problems()
        if problems:
            self.status.show_message(problems[0], "warn")
        else:
            self.status.show_message("Ready to sign in.", "muted")
        self.sign_in.setEnabled(not problems)

    # -- actions -----------------------------------------------------------

    def _sign_in(self) -> None:
        if self._busy:
            return
        credentials = self._credentials()
        problems = credentials.problems()
        if problems:
            self.status.show_message("; ".join(problems), "error")
            return

        self._busy = True
        self.sign_in.setEnabled(False)
        self.status.show_message("Checking with Commons…", "info")

        worker = _LoginWorker(credentials)
        worker.signals.finished.connect(
            lambda result, c=credentials: self._finished(result, c)
        )
        start(worker)

    def _finished(self, result, credentials) -> None:
        self._busy = False
        self.sign_in.setEnabled(True)

        if not result.ok:
            self.status.show_message(result.message, "error")
            # Never leave a rejected password behind on disk.
            auth.clear_pywikibot_config()
            return

        if self.remember_box.isChecked():
            try:
                auth.save(credentials)
            except auth.AuthError as exc:
                self.status.show_message(
                    f"{result.message} The password could not be stored: {exc}",
                    "warn",
                )
                self.logged_in.emit(result.username)
                return

        self.forget_button.setEnabled(True)
        self.status.show_message(result.message, "good")
        self.logged_in.emit(result.username)

    def _forget(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        answer = QMessageBox.question(
            self, "Forget the password",
            "Remove the stored password from this computer?\n\n"
            "The bot password itself stays valid — cancel it at "
            "Special:BotPasswords if you want it gone for good.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        auth.forget(self.username_field.text().strip())
        auth.clear_pywikibot_config()
        self.password_field.clear()
        self.forget_button.setEnabled(False)
        self.status.show_message("Removed from this computer.", "muted")
