"""Logging in to Wikimedia Commons.

Telling a volunteer to run ``pywikibot login`` in a terminal and hand-edit a
``user-config.py`` is a real barrier, so the app does it: the user types a
username and a bot password, and everything underneath is written for them.

Two rules shape this module. Credentials go to the operating system's
keychain rather than a file in the project, and only ever a **bot password** —
a revocable, scope-limited credential created at Special:BotPasswords — never
the account's own password. If the keychain is unavailable the user is told,
rather than the secret being quietly written to disk.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

SERVICE = "vcut-gui.commons"
#: Where a bot password is created. Shown in the login window.
BOT_PASSWORD_URL = "https://commons.wikimedia.org/wiki/Special:BotPasswords"

#: A bot password login is "User@botname", and the secret is 32+ chars.
BOT_USERNAME_RE = re.compile(r"^[^@]+@[^@]+$")


class AuthError(RuntimeError):
    """Raised when credentials cannot be stored or used."""


@dataclass
class Credentials:
    """A Commons bot password."""

    username: str = ""
    password: str = ""
    family: str = "commons"
    code: str = "commons"

    @property
    def account(self) -> str:
        """The account name, without the bot-password suffix."""
        return self.username.split("@", 1)[0] if self.username else ""

    @property
    def bot_name(self) -> str:
        return self.username.split("@", 1)[1] if "@" in self.username else ""

    @property
    def looks_like_bot_password(self) -> bool:
        return bool(BOT_USERNAME_RE.match(self.username or ""))

    def problems(self) -> list[str]:
        """Anything that would stop this credential working."""
        found = []
        if not self.username.strip():
            found.append("no username")
        elif not self.looks_like_bot_password:
            found.append(
                "a bot password login looks like 'YourName@vcut' — create one "
                "at Special:BotPasswords"
            )
        if not self.password.strip():
            found.append("no password")
        elif len(self.password.strip()) < 16:
            found.append(
                "that looks too short for a bot password; it should be a long "
                "generated string, not your account password"
            )
        return found


# -- storage ---------------------------------------------------------------


def keyring_available() -> bool:
    """Whether a real system keychain can be reached."""
    try:
        import keyring
        from keyring.backends import fail
    except ImportError:
        return False
    try:
        backend = keyring.get_keyring()
    except Exception:  # noqa: BLE001 - any backend problem means unavailable
        return False
    return not isinstance(backend, fail.Keyring)


def keyring_name() -> str:
    try:
        import keyring

        return type(keyring.get_keyring()).__name__
    except Exception:  # noqa: BLE001
        return "none"


def save(credentials: Credentials) -> None:
    """Put the password in the system keychain."""
    if not keyring_available():
        raise AuthError(
            "No system keychain is available, so the password cannot be "
            "stored safely. Install a keyring backend, or log in through "
            "Pywikibot directly."
        )
    import keyring

    try:
        keyring.set_password(SERVICE, credentials.username, credentials.password)
    except Exception as exc:  # noqa: BLE001 - backends raise many types
        raise AuthError(f"could not store the password: {exc}") from exc

    _remember_username(credentials.username)


def load(username: str = "") -> Credentials | None:
    """Read stored credentials, if there are any."""
    username = username or _remembered_username()
    if not username or not keyring_available():
        return None
    import keyring

    try:
        password = keyring.get_password(SERVICE, username)
    except Exception:  # noqa: BLE001
        return None
    if not password:
        return None
    return Credentials(username=username, password=password)


def forget(username: str = "") -> None:
    """Remove stored credentials."""
    username = username or _remembered_username()
    if username and keyring_available():
        import keyring

        try:
            keyring.delete_password(SERVICE, username)
        except Exception:  # noqa: BLE001 - already gone is fine
            pass
    _remember_username("")


def _username_file() -> Path:
    from .settings import config_directory

    return config_directory() / "commons-user.txt"


def _remember_username(username: str) -> None:
    """The username is not secret; only the password goes to the keychain."""
    path = _username_file()
    try:
        if username:
            path.write_text(username, encoding="utf-8")
        elif path.exists():
            path.unlink()
    except OSError:
        pass


def _remembered_username() -> str:
    try:
        return _username_file().read_text(encoding="utf-8").strip()
    except OSError:
        return ""


# -- pywikibot wiring ------------------------------------------------------


def pywikibot_directory() -> Path:
    """Where the generated Pywikibot configuration lives."""
    from .settings import config_directory

    path = config_directory() / "pywikibot"
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_pywikibot_config(credentials: Credentials) -> Path:
    """Generate the config and password files Pywikibot expects.

    Doing this by hand is the step that stops most people, so the app writes
    both. The password file is created with owner-only permissions.
    """
    directory = pywikibot_directory()

    config = directory / "user-config.py"
    config.write_text(
        "# Written by vcut. Edit through the app rather than by hand.\n"
        f'family = "{credentials.family}"\n'
        f'mylang = "{credentials.code}"\n'
        f'usernames["{credentials.family}"]["{credentials.code}"] = '
        f'"{credentials.account}"\n'
        'password_file = "user-password.py"\n'
        "put_throttle = 1\n",
        encoding="utf-8",
    )

    secrets = directory / "user-password.py"
    secrets.write_text(
        f'("{credentials.account}", BotPassword('
        f'"{credentials.bot_name}", "{credentials.password}"))\n',
        encoding="utf-8",
    )
    try:
        secrets.chmod(0o600)
    except OSError:
        pass

    return directory


def clear_pywikibot_config() -> None:
    """Remove the generated configuration, password file included."""
    directory = pywikibot_directory()
    for name in ("user-config.py", "user-password.py", "throttle.ctrl"):
        try:
            (directory / name).unlink()
        except OSError:
            pass


@dataclass
class LoginResult:
    """What happened when we tried to log in."""

    ok: bool = False
    username: str = ""
    message: str = ""
    site: str = ""


def verify(credentials: Credentials, *, timeout: float = 30.0) -> LoginResult:
    """Actually log in, to prove the credentials work.

    Runs in a separate process so a hung network call or a Pywikibot that
    decides to prompt on stdin cannot freeze the window.
    """
    import json
    import subprocess
    import sys

    problems = credentials.problems()
    if problems:
        return LoginResult(message="; ".join(problems))

    directory = write_pywikibot_config(credentials)
    script = (
        "import json, os, sys\n"
        "os.environ['PYWIKIBOT_DIR'] = sys.argv[1]\n"
        "os.environ['PYWIKIBOT_NO_USER_CONFIG'] = '0'\n"
        "try:\n"
        "    import pywikibot\n"
        "    site = pywikibot.Site(sys.argv[3], sys.argv[2])\n"
        "    site.login()\n"
        "    user = site.user()\n"
        "    print(json.dumps({'ok': bool(user), 'user': user or '',\n"
        "                      'site': str(site)}))\n"
        "except Exception as exc:\n"
        "    print(json.dumps({'ok': False, 'error': f'{type(exc).__name__}: {exc}'}))\n"
    )

    try:
        result = subprocess.run(
            [sys.executable, "-c", script, str(directory),
             credentials.family, credentials.code],
            capture_output=True, text=True, timeout=timeout,
            stdin=subprocess.DEVNULL, check=False,
        )
    except subprocess.TimeoutExpired:
        return LoginResult(message="Commons did not answer in time.")
    except OSError as exc:
        return LoginResult(message=f"could not start the login check: {exc}")

    line = (result.stdout or "").strip().splitlines()
    payload = {}
    for candidate in reversed(line):
        try:
            payload = json.loads(candidate)
            break
        except json.JSONDecodeError:
            continue

    if not payload:
        detail = (result.stderr or "").strip().splitlines()
        return LoginResult(
            message=detail[-1][:300] if detail else "the login check said nothing"
        )

    if payload.get("ok"):
        return LoginResult(
            ok=True, username=payload.get("user", ""),
            site=payload.get("site", ""),
            message=f"Logged in as {payload.get('user', '')}.",
        )
    return LoginResult(message=payload.get("error", "login refused"))
