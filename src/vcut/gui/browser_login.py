"""Signing in through Commons' own login page.

Passkeys cannot work from a desktop form. The WebAuthn challenge Commons
issues is bound to ``rpId: commons.wikimedia.org``, so only a browser on
that origin can answer it — the same is true of two-factor codes and any
future login method the wiki adds.

So instead of reimplementing the login, this shows the real page in an
embedded browser. Whatever Commons asks for — password, passkey, 2FA — is
answered by its own interface, and when the session cookies appear the app
takes them. Nothing is typed into a form this app controls.

The result is a session, not a stored password. Sessions expire, so this
suits uploading now; a bot password remains the way to be signed in across
days.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

LOGIN_URL = "https://commons.wikimedia.org/wiki/Special:UserLogin"
API_URL = "https://commons.wikimedia.org/w/api.php"
#: Wikimedia asks tools to identify themselves.
USER_AGENT = "vcut-gui (https://github.com/Wikimedians-of-Kerala/vcut-gui)"

#: Cookies MediaWiki sets once a login has completed.
SESSION_COOKIES = ("commonswikiUserID", "commonswikiUserName", "commonswikiSession")


def webengine_available() -> bool:
    """Whether an embedded browser can be shown."""
    import importlib.util

    return importlib.util.find_spec("PySide6.QtWebEngineWidgets") is not None


@dataclass
class Session:
    """A logged-in browser session, as cookies."""

    username: str = ""
    cookies: dict[str, str] = field(default_factory=dict)

    @property
    def is_complete(self) -> bool:
        """Whether the cookies identify a logged-in user."""
        return bool(self.username) and "commonswikiSession" in self.cookies

    def cookie_header(self) -> str:
        return "; ".join(f"{name}={value}" for name, value in self.cookies.items())

    def to_dict(self) -> dict:
        return {"username": self.username, "cookies": dict(self.cookies)}


def session_file():
    from ..settings import config_directory

    return config_directory() / "commons-session.json"


def save_session(session: Session) -> None:
    """Keep the session so the browser is not needed every time.

    These cookies are as good as being logged in, so the file is written
    owner-only — and it is a session, not a password: it expires.
    """
    path = session_file()
    try:
        path.write_text(json.dumps(session.to_dict(), indent=2), encoding="utf-8")
        path.chmod(0o600)
    except OSError:
        pass


def load_session() -> Session | None:
    path = session_file()
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    session = Session(
        username=payload.get("username", ""),
        cookies=payload.get("cookies", {}) or {},
    )
    return session if session.is_complete else None


def forget_session() -> None:
    try:
        session_file().unlink()
    except OSError:
        pass


def csrf_token(session: Session, *, timeout: float = 20.0) -> str:
    """Fetch an edit token for this session.

    This is the real test of whether captured cookies can write: an
    anonymous caller gets the placeholder ``+\\``, while a logged-in one
    gets a long token. Without it an upload cannot be made.
    """
    import httpx

    try:
        response = httpx.get(
            API_URL,
            params={"action": "query", "meta": "tokens",
                    "type": "csrf", "format": "json"},
            headers={"Cookie": session.cookie_header(),
                     "User-Agent": USER_AGENT},
            timeout=timeout, follow_redirects=True,
        )
        token = response.json()["query"]["tokens"]["csrftoken"]
    except Exception:  # noqa: BLE001
        return ""
    return "" if token in ("+\\", "") else str(token)


def can_upload(session: Session) -> bool:
    """Whether this session is good enough to upload with."""
    return bool(csrf_token(session))


def whoami(session: Session, *, timeout: float = 20.0) -> str:
    """Ask Commons who these cookies belong to; empty means not logged in."""
    import httpx

    try:
        response = httpx.get(
            API_URL,
            params={"action": "query", "meta": "userinfo", "format": "json"},
            headers={"Cookie": session.cookie_header(),
                     "User-Agent": USER_AGENT},
            timeout=timeout, follow_redirects=True,
        )
        payload = response.json()
    except Exception:  # noqa: BLE001 - any failure means "cannot confirm"
        return ""

    info = payload.get("query", {}).get("userinfo", {})
    # An anonymous user comes back flagged, with an IP for a name.
    if "anon" in info:
        return ""
    return str(info.get("name", ""))


# -- the window ------------------------------------------------------------


def make_browser_page(parent=None):
    """A browser widget pointed at the Commons login page.

    Returns ``(widget, profile)``. The profile keeps its own cookie jar, so
    signing out here does not disturb the user's real browser.
    """
    from PySide6.QtWebEngineCore import QWebEngineProfile
    from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: F401

    from ..settings import cache_directory

    profile = QWebEngineProfile("vcut-commons", parent)
    storage = cache_directory() / "browser"
    storage.mkdir(parents=True, exist_ok=True)
    profile.setPersistentStoragePath(str(storage))
    profile.setCachePath(str(storage / "cache"))
    # Persistent cookies let a signed-in session survive a restart.
    profile.setPersistentCookiesPolicy(
        QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
    )

    view = QWebEngineView(parent)
    from PySide6.QtWebEngineCore import QWebEnginePage

    view.setPage(QWebEnginePage(profile, view))
    return view, profile


def upload_with_session(session: Session, path, filename: str, wikitext: str,
                        *, comment: str = "", timeout: float = 600.0) -> str:
    """Upload a file using captured browser cookies.

    This is what makes a browser login worth having: the same cookies the
    wiki handed the browser are used directly against the API, so a passkey
    or 2FA login ends in a working upload without Pywikibot or a stored
    password.
    """
    from pathlib import Path

    import httpx

    token = csrf_token(session, timeout=30)
    if not token:
        raise RuntimeError(
            "the browser session is no longer signed in — sign in again"
        )

    source = Path(path)
    if not source.is_file():
        raise RuntimeError(f"file not found: {source}")

    headers = {"Cookie": session.cookie_header(), "User-Agent": USER_AGENT}
    data = {
        "action": "upload",
        "filename": filename,
        "text": wikitext,
        "comment": comment or "Uploading a conference session recording",
        "token": token,
        "format": "json",
    }

    with source.open("rb") as handle:
        files = {"file": (filename, handle, "application/octet-stream")}
        try:
            response = httpx.post(
                API_URL, data=data, files=files, headers=headers,
                timeout=timeout, follow_redirects=True,
            )
            payload = response.json()
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"upload failed: {exc}") from exc

    if "error" in payload:
        error = payload["error"]
        raise RuntimeError(f"{error.get('code', 'error')}: {error.get('info', '')}")

    result = payload.get("upload", {})
    if result.get("result") != "Success":
        warnings = result.get("warnings", {})
        if warnings:
            raise RuntimeError(f"Commons warned: {', '.join(warnings)}")
        raise RuntimeError(f"upload did not succeed: {result.get('result', '?')}")

    return str(result.get("filename", filename))
