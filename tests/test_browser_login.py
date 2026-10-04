"""Signing in through the wiki's own login page."""

import json

import pytest

pytest.importorskip("PySide6")

from vcut.gui import browser_login  # noqa: E402


def session(**kwargs):
    base = {
        "username": "Ranjithsiji",
        "cookies": {"commonswikiSession": "abc", "commonswikiUserName": "Ranjithsiji"},
    }
    base.update(kwargs)
    return browser_login.Session(**base)


def test_a_session_needs_the_session_cookie():
    assert session().is_complete
    assert not browser_login.Session(username="X", cookies={}).is_complete
    assert not session(username="").is_complete


def test_the_cookie_header_is_what_http_expects():
    header = session().cookie_header()
    assert "commonswikiSession=abc" in header
    assert "; " in header


def test_a_session_survives_being_stored(tmp_path, monkeypatch):
    monkeypatch.setattr(browser_login, "session_file", lambda: tmp_path / "s.json")
    browser_login.save_session(session())
    loaded = browser_login.load_session()
    assert loaded is not None
    assert loaded.username == "Ranjithsiji"
    assert loaded.cookies["commonswikiSession"] == "abc"


def test_the_stored_session_is_not_world_readable(tmp_path, monkeypatch):
    import sys

    if sys.platform == "win32":
        return
    path = tmp_path / "s.json"
    monkeypatch.setattr(browser_login, "session_file", lambda: path)
    browser_login.save_session(session())
    # These cookies are as good as a password while they last.
    assert path.stat().st_mode & 0o777 == 0o600


def test_an_incomplete_stored_session_is_ignored(tmp_path, monkeypatch):
    path = tmp_path / "s.json"
    monkeypatch.setattr(browser_login, "session_file", lambda: path)
    path.write_text(json.dumps({"username": "", "cookies": {}}), encoding="utf-8")
    assert browser_login.load_session() is None


def test_a_corrupt_stored_session_is_ignored(tmp_path, monkeypatch):
    path = tmp_path / "s.json"
    monkeypatch.setattr(browser_login, "session_file", lambda: path)
    path.write_text("not json", encoding="utf-8")
    assert browser_login.load_session() is None


def test_forgetting_removes_the_file(tmp_path, monkeypatch):
    path = tmp_path / "s.json"
    monkeypatch.setattr(browser_login, "session_file", lambda: path)
    browser_login.save_session(session())
    browser_login.forget_session()
    assert not path.exists()


def test_the_anonymous_csrf_placeholder_means_not_signed_in(monkeypatch):
    # MediaWiki hands anonymous callers "+\", which cannot write.
    import httpx

    class Response:
        @staticmethod
        def json():
            return {"query": {"tokens": {"csrftoken": "+\\"}}}

    monkeypatch.setattr(httpx, "get", lambda *a, **k: Response())
    assert browser_login.csrf_token(session()) == ""
    assert browser_login.can_upload(session()) is False


def test_a_real_token_means_the_session_can_upload(monkeypatch):
    import httpx

    class Response:
        @staticmethod
        def json():
            return {"query": {"tokens": {"csrftoken": "abc123+\\"}}}

    monkeypatch.setattr(httpx, "get", lambda *a, **k: Response())
    assert browser_login.can_upload(session()) is True


def test_uploading_without_a_live_session_is_refused(monkeypatch, tmp_path):
    monkeypatch.setattr(browser_login, "csrf_token", lambda *a, **k: "")
    target = tmp_path / "clip.webm"
    target.write_bytes(b"x")
    with pytest.raises(RuntimeError, match="no longer signed in"):
        browser_login.upload_with_session(session(), target, "A.webm", "text")


def test_uploading_a_missing_file_is_refused(monkeypatch, tmp_path):
    monkeypatch.setattr(browser_login, "csrf_token", lambda *a, **k: "token")
    with pytest.raises(RuntimeError, match="file not found"):
        browser_login.upload_with_session(
            session(), tmp_path / "gone.webm", "A.webm", "text"
        )


def test_the_login_page_is_the_real_commons_one():
    assert browser_login.LOGIN_URL.startswith("https://commons.wikimedia.org/")
    assert "Special:UserLogin" in browser_login.LOGIN_URL
