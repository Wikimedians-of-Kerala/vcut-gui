"""Uploading finished clips to Wikimedia Commons with Pywikibot.

Pywikibot is an optional dependency and needs its own one-time login, so it is
imported lazily and every failure is reported as something the user can act on
rather than a traceback.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .commons import CommonsFile
from .ffmpeg import OutputFormat

#: Extensions Commons accepts for video.
#: https://commons.wikimedia.org/wiki/Commons:File_types#Video
ALLOWED_EXTENSIONS = {"webm", "ogv", "ogg", "mpg", "mpeg"}

#: Commons rejects uploads above this size without a special workflow.
MAX_UPLOAD_BYTES = 4 * 1024 ** 3  # 4 GiB


class UploadError(RuntimeError):
    """Raised when an upload cannot be attempted or fails."""


@dataclass
class LoginStatus:
    """Whether Commons can be uploaded to, by whichever route."""

    available: bool = False
    logged_in: bool = False
    username: str = ""
    site: str = ""
    message: str = ""
    #: "pywikibot" or "browser" -- which sign-in is being used. A browser
    #: session is what a passkey or two-factor account ends up with.
    method: str = ""


def _use_generated_config() -> None:
    """Point Pywikibot at the configuration the login window wrote.

    Without this it looks in the current directory, which is wherever the
    app happened to be started from.
    """
    import os

    from .auth import pywikibot_directory

    directory = pywikibot_directory()
    if (directory / "user-config.py").is_file():
        os.environ.setdefault("PYWIKIBOT_DIR", str(directory))


def pywikibot_available() -> bool:
    try:
        _use_generated_config()
        import pywikibot  # noqa: F401
    except ImportError:
        return False
    return True


def _browser_login() -> LoginStatus | None:
    """A signed-in browser session, if one was saved and still works.

    Accounts with a passkey or two-factor sign-in can only log in through
    the wiki's own page, so this is the route they end up on. Checking
    Pywikibot alone reported them as signed out while the login window said
    they were signed in.
    """
    try:
        from .gui import browser_login
    except ImportError:
        return None

    try:
        session = browser_login.load_session()
        if session is None:
            return None
        if not browser_login.can_upload(session):
            return LoginStatus(
                available=True,
                method="browser",
                username=session.username,
                site="commons:commons",
                message=(
                    f"The browser session for {session.username} has expired. "
                    f"Sign in again, or use a bot password."
                ),
            )
        return LoginStatus(
            available=True, logged_in=True, method="browser",
            username=session.username, site="commons:commons",
            message=f"Signed in to Commons as {session.username} (browser session).",
        )
    except Exception:  # noqa: BLE001 - a bad session must not break the check
        return None


def check_login(family: str = "commons", code: str = "commons") -> LoginStatus:
    """Report whether we can upload, without raising.

    Either route counts: a bot password through Pywikibot, or a browser
    session saved by the login window.
    """
    browser = _browser_login()
    if browser is not None and browser.logged_in:
        return browser

    if not pywikibot_available():
        if browser is not None:
            return browser
        return LoginStatus(
            message=(
                "Pywikibot is not installed. Install it with "
                "'uv pip install pywikibot' to enable uploading."
            )
        )

    # A working bot password beats a stale browser session, so Pywikibot is
    # tried next. Its answer is kept only if it is actually signed in: when
    # neither route works, an expired session is the more useful thing to
    # say, since it names the account and what went wrong with it.
    pywikibot_status = _pywikibot_login(family, code)
    if pywikibot_status.logged_in or browser is None:
        return pywikibot_status
    return browser


def _pywikibot_login(family: str, code: str) -> LoginStatus:
    """Whether a bot password is configured and accepted."""

    from .auth import load as load_credentials

    stored = load_credentials()

    import pywikibot

    try:
        site = pywikibot.Site(code, family)
        user = site.username()
        if not user:
            hint = (
                "Not signed in to Commons yet — use Sign in to Commons."
                if stored is None else
                f"Stored credentials for {stored.account} were not accepted; "
                f"sign in again."
            )
            return LoginStatus(available=True, site=str(site), message=hint)
        return LoginStatus(
            available=True, logged_in=True, method="pywikibot",
            username=str(user), site=str(site),
            message=f"Logged in to {site} as {user}.",
        )
    except Exception as exc:  # noqa: BLE001 - pywikibot raises many types
        return LoginStatus(
            available=True,
            message=f"Pywikibot could not reach Commons: {exc}",
        )


def validate_for_upload(prepared: CommonsFile) -> list[str]:
    """Return blocking problems that must be fixed before uploading."""
    problems: list[str] = []
    path = Path(prepared.local_path) if prepared.local_path else None

    if not path:
        problems.append("no file has been produced for this clip yet")
    elif not path.is_file():
        problems.append(f"file not found: {path}")
    else:
        extension = path.suffix.lstrip(".").lower()
        if extension not in ALLOWED_EXTENSIONS:
            problems.append(
                f"Commons does not accept .{extension} files — "
                f"convert this clip to WebM first"
            )
        size = path.stat().st_size
        if size == 0:
            problems.append("the file is empty")
        elif size > MAX_UPLOAD_BYTES:
            problems.append(
                f"the file is {size / 1024 ** 3:.1f} GiB, above the 4 GiB upload limit"
            )

    if not prepared.filename:
        problems.append("no Commons filename")
    if not prepared.wikitext.strip():
        problems.append("no file description")
    if any("DO NOT RECORD" in warning for warning in prepared.warnings):
        problems.append("the schedule marks this session as do-not-record")

    return problems


def upload_file(
    prepared: CommonsFile,
    *,
    comment: str = "",
    ignore_warnings: bool = False,
    dry_run: bool = False,
    family: str = "commons",
    code: str = "commons",
) -> str:
    """Upload one prepared file. Returns a short status message."""
    problems = validate_for_upload(prepared)
    if problems:
        raise UploadError("; ".join(problems))

    if dry_run:
        return f"would upload as {prepared.filename}"

    # A browser session is preferred when there is one: it is how an account
    # with a passkey or two-factor sign-in gets here at all.
    session_result = _try_browser_session(prepared, comment)
    if session_result is not None:
        return session_result

    if not pywikibot_available():
        raise UploadError(
            "Pywikibot is not installed. Install it with 'uv pip install pywikibot'."
        )

    import pywikibot
    from pywikibot.specialbots import UploadRobot

    try:
        site = pywikibot.Site(code, family)
        if not site.username():
            raise UploadError(
                "Pywikibot is not logged in. Run 'pywikibot login' and try again."
            )

        page = pywikibot.FilePage(site, prepared.filename)
        if page.exists():
            raise UploadError(f"'{prepared.filename}' already exists on Commons")

        bot = UploadRobot(
            [prepared.local_path],
            description=prepared.wikitext,
            use_filename=prepared.filename,
            keep_filename=True,
            verify_description=False,
            ignore_warning=ignore_warnings,
            target_site=site,
            summary=comment or DEFAULT_COMMENT,
        )
        bot.run()
    except UploadError:
        raise
    except Exception as exc:  # noqa: BLE001 - pywikibot raises many types
        raise UploadError(f"upload failed: {exc}") from exc

    return f"uploaded as {prepared.filename}"


#: The change tag to mark uploads with, so a batch can be found in the
#: recent-changes feed and in file histories.
#:
#: A tag only works once an administrator has defined it on the wiki, at
#: Special:Tags. Sending an undefined one makes the upload fail outright, so
#: this is checked against the wiki rather than assumed, and the result is
#: remembered for the session.
CHANGE_TAG = "Vcut"

#: The edit summary when the user has not written one. It names the tool, so
#: a file's history says where it came from even where the change tag is not
#: available.
DEFAULT_COMMENT = "Uploaded with vcut"

_tag_allowed: bool | None = None


def tag_is_available(session=None) -> bool:
    """Whether this wiki accepts :data:`CHANGE_TAG` on an upload.

    Asked once. An undefined tag is not an error worth failing an upload
    over -- the file is what matters -- so an unavailable tag is simply not
    sent.
    """
    global _tag_allowed
    if _tag_allowed is not None:
        return _tag_allowed

    _tag_allowed = False
    try:
        import httpx

        response = httpx.get(
            "https://commons.wikimedia.org/w/api.php",
            params={
                "action": "paraminfo", "modules": "upload",
                "format": "json", "formatversion": "2",
            },
            timeout=10,
            headers={"User-Agent": _user_agent()},
        )
        response.raise_for_status()
        for parameter in response.json()["paraminfo"]["modules"][0]["parameters"]:
            if parameter["name"] == "tags":
                _tag_allowed = CHANGE_TAG in (parameter.get("type") or [])
                break
    except Exception:  # noqa: BLE001 - never fail an upload over this
        _tag_allowed = False
    return _tag_allowed


def _user_agent() -> str:
    from .gui.browser_login import USER_AGENT

    return USER_AGENT


def _try_browser_session(prepared: CommonsFile, comment: str) -> str | None:
    """Upload with captured browser cookies, or return ``None`` to fall back."""
    try:
        from .gui import browser_login
    except ImportError:
        return None

    session = browser_login.load_session()
    if session is None:
        return None
    if not browser_login.can_upload(session):
        # Expired: say so rather than silently trying something else.
        raise UploadError(
            "the browser session has expired — sign in to Commons again"
        )

    try:
        name = browser_login.upload_with_session(
            session, prepared.local_path, prepared.filename,
            prepared.wikitext, comment=comment,
            tags=CHANGE_TAG if tag_is_available() else "",
        )
    except RuntimeError as exc:
        raise UploadError(str(exc)) from exc
    return f"uploaded as {name}"


def commons_url(filename: str) -> str:
    from urllib.parse import quote

    return f"https://commons.wikimedia.org/wiki/File:{quote(filename.replace(' ', '_'))}"


def suggested_format_hint(fmt: OutputFormat) -> str:
    """Explain whether a format can be uploaded as-is."""
    if fmt.commons_compatible:
        return "Ready to upload to Commons."
    return "Commons rejects MP4 — convert these clips before uploading."
