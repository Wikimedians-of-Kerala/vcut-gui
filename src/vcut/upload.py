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
    """Whether Pywikibot is installed and logged in."""

    available: bool = False
    logged_in: bool = False
    username: str = ""
    site: str = ""
    message: str = ""


def pywikibot_available() -> bool:
    try:
        import pywikibot  # noqa: F401
    except ImportError:
        return False
    return True


def check_login(family: str = "commons", code: str = "commons") -> LoginStatus:
    """Report whether we can upload, without raising."""
    if not pywikibot_available():
        return LoginStatus(
            message=(
                "Pywikibot is not installed. Install it with "
                "'uv pip install pywikibot' to enable uploading."
            )
        )

    import pywikibot

    try:
        site = pywikibot.Site(code, family)
        user = site.username()
        if not user:
            return LoginStatus(
                available=True, site=str(site),
                message=(
                    "Pywikibot is installed but not logged in. Run "
                    "'pywikibot login' in a terminal, then try again."
                ),
            )
        return LoginStatus(
            available=True, logged_in=True, username=str(user), site=str(site),
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
            summary=comment or "Uploading conference session recording",
        )
        bot.run()
    except UploadError:
        raise
    except Exception as exc:  # noqa: BLE001 - pywikibot raises many types
        raise UploadError(f"upload failed: {exc}") from exc

    return f"uploaded as {prepared.filename}"


def commons_url(filename: str) -> str:
    from urllib.parse import quote

    return f"https://commons.wikimedia.org/wiki/File:{quote(filename.replace(' ', '_'))}"


def suggested_format_hint(fmt: OutputFormat) -> str:
    """Explain whether a format can be uploaded as-is."""
    if fmt.commons_compatible:
        return "Ready to upload to Commons."
    return "Commons rejects MP4 — convert these clips before uploading."
