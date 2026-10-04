"""The embedded browser used to sign in to Commons.

Shows the wiki's real login page and watches its cookie jar. When the
cookies that mean "logged in" appear, the session is captured and confirmed
against the API, so the user is told whether it can actually upload rather
than being left to find out later.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, QUrl, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import browser_login, icons
from .widgets import StatusLabel
from .workers import start


class _ConfirmSignals(QObject):
    done = Signal(str, bool)      # username, can upload


class _ConfirmWorker(QRunnable):
    """Ask Commons who we are, without blocking the window."""

    def __init__(self, session: browser_login.Session) -> None:
        super().__init__()
        self.signals = _ConfirmSignals()
        self._session = session

    def run(self) -> None:
        name = browser_login.whoami(self._session)
        uploadable = bool(name) and browser_login.can_upload(self._session)
        self.signals.done.emit(name, uploadable)


class BrowserLoginWindow(QDialog):
    """Commons' own login page, in a window."""

    signed_in = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Sign in to Wikimedia Commons")
        self.resize(900, 760)
        self._captured: browser_login.Session | None = None
        self._cookies: dict[str, str] = {}
        self._confirming = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        hint = QLabel(
            "Sign in as you normally would — password, passkey or two-factor "
            "all work here. The window closes itself once you are in."
        )
        hint.setWordWrap(True)
        hint.setObjectName("screenSubheading")
        layout.addWidget(hint)

        self.view, self.profile = browser_login.make_browser_page(self)
        self.view.load(QUrl(browser_login.LOGIN_URL))
        layout.addWidget(self.view, 1)

        store = self.profile.cookieStore()
        store.cookieAdded.connect(self._cookie_added)

        self.status = StatusLabel("Waiting for you to sign in…", "muted")
        layout.addWidget(self.status)

        buttons = QHBoxLayout()
        reload_button = QPushButton("Reload")
        reload_button.setAutoDefault(False)
        icons.apply(reload_button, "refresh")
        reload_button.clicked.connect(
            lambda: self.view.load(QUrl(browser_login.LOGIN_URL))
        )
        buttons.addWidget(reload_button)
        buttons.addStretch(1)

        self.close_button = QPushButton("Cancel")
        self.close_button.setAutoDefault(False)
        icons.apply(self.close_button, "cancel")
        self.close_button.clicked.connect(self.reject)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)

    # -- cookie watching ---------------------------------------------------

    def _cookie_added(self, cookie) -> None:
        name = bytes(cookie.name()).decode("utf-8", "replace")
        value = bytes(cookie.value()).decode("utf-8", "replace")
        self._cookies[name] = value

        # Only act once the cookie that marks a completed login appears.
        if "commonswikiSession" not in self._cookies:
            return
        if "commonswikiUserName" not in self._cookies:
            return
        if self._confirming:
            return

        self._confirming = True
        username = self._cookies.get("commonswikiUserName", "").replace("_", " ")
        session = browser_login.Session(username=username, cookies=dict(self._cookies))
        self.status.show_message("Signed in — checking the session…", "info")

        worker = _ConfirmWorker(session)
        worker.signals.done.connect(
            lambda name_, ok, s=session: self._confirmed(s, name_, ok)
        )
        start(worker)

    def _confirmed(self, session, username: str, uploadable: bool) -> None:
        self._confirming = False
        if not username:
            self.status.show_message(
                "The browser signed in, but Commons did not recognise the "
                "session. Try reloading.", "warn",
            )
            return

        session.username = username
        browser_login.save_session(session)
        self._captured = session

        if uploadable:
            self.status.show_message(
                f"Signed in as {username}. This session can upload.", "good"
            )
        else:
            self.status.show_message(
                f"Signed in as {username}, but the session cannot upload — "
                f"your account may lack upload rights.", "warn",
            )
        self.signed_in.emit(username)
        self.accept()

    @property
    def session(self):
        return self._captured

    def closeEvent(self, event) -> None:  # noqa: N802
        # Qt requires the page to go before its profile, or it warns and can
        # crash on exit.
        page = self.view.page()
        self.view.setPage(None)
        if page is not None:
            page.deleteLater()
        super().closeEvent(event)
