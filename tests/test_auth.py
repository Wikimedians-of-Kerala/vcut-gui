"""Commons credentials."""

from vcut.auth import BOT_PASSWORD_URL, Credentials, write_pywikibot_config


def good():
    return Credentials(username="Ranjithsiji@vcut", password="k" * 32)


def test_a_bot_password_login_is_split_into_account_and_bot():
    credentials = good()
    assert credentials.account == "Ranjithsiji"
    assert credentials.bot_name == "vcut"


def test_a_valid_credential_has_no_problems():
    assert good().problems() == []


def test_an_account_password_is_rejected():
    # The whole point is to never hold the real account password.
    problems = Credentials(username="Ranjithsiji", password="hunter2").problems()
    assert any("Special:BotPasswords" in p for p in problems)


def test_a_short_password_is_questioned():
    problems = Credentials(username="A@b", password="short").problems()
    assert any("too short" in p for p in problems)


def test_empty_credentials_are_rejected():
    assert len(Credentials().problems()) == 2


def test_the_help_link_points_at_bot_passwords():
    assert BOT_PASSWORD_URL.endswith("Special:BotPasswords")


def test_the_generated_config_names_the_account_not_the_login(tmp_path, monkeypatch):
    import vcut.auth as module

    monkeypatch.setattr(module, "pywikibot_directory", lambda: tmp_path)
    write_pywikibot_config(good())
    config = (tmp_path / "user-config.py").read_text(encoding="utf-8")
    # Pywikibot wants the bare account name here, not "Name@bot".
    assert '"Ranjithsiji"' in config
    assert "Ranjithsiji@vcut" not in config


def test_the_password_file_holds_the_bot_name_and_secret(tmp_path, monkeypatch):
    import vcut.auth as module

    monkeypatch.setattr(module, "pywikibot_directory", lambda: tmp_path)
    write_pywikibot_config(good())
    secrets = (tmp_path / "user-password.py").read_text(encoding="utf-8")
    assert 'BotPassword("vcut"' in secrets
    assert "k" * 32 in secrets


def test_the_password_file_is_not_world_readable(tmp_path, monkeypatch):
    import sys

    import vcut.auth as module

    if sys.platform == "win32":
        return
    monkeypatch.setattr(module, "pywikibot_directory", lambda: tmp_path)
    write_pywikibot_config(good())
    mode = (tmp_path / "user-password.py").stat().st_mode & 0o777
    assert mode == 0o600


def test_clearing_removes_the_secret(tmp_path, monkeypatch):
    import vcut.auth as module

    monkeypatch.setattr(module, "pywikibot_directory", lambda: tmp_path)
    write_pywikibot_config(good())
    module.clear_pywikibot_config()
    assert not (tmp_path / "user-password.py").exists()
    assert not (tmp_path / "user-config.py").exists()
