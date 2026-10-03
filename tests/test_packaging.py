"""The packaging configuration.

These catch the mistakes that only show up in a built package, where a full
PyInstaller run takes minutes.
"""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


# -- the spec --------------------------------------------------------------


def test_the_bundle_uses_a_wrapper_entry_point():
    # PyInstaller runs its entry script as a top-level module, so pointing it
    # at src/vcut/gui/app.py breaks that file's relative imports at runtime.
    spec = read("vcut-gui.spec")
    assert "packaging/entry.py" in spec
    assert '["src/vcut/gui/app.py"]' not in spec


def test_the_entry_point_imports_through_the_package():
    entry = read("packaging/entry.py")
    assert "from vcut.gui.app import main" in entry
    assert "from ." not in entry


def test_the_logo_is_bundled():
    assert '("src/vcut/gui/logo", "vcut/gui/logo")' in read("vcut-gui.spec")


def test_the_screens_are_listed_as_hidden_imports():
    # They are only reached through the window, so PyInstaller cannot see them.
    spec = read("vcut-gui.spec")
    for module in ("screen_setup", "screen_verify", "screen_metadata", "screen_upload"):
        assert f"vcut.gui.{module}" in spec


def test_the_bundle_opens_without_a_console():
    assert "console=False" in read("vcut-gui.spec")


# -- project metadata ------------------------------------------------------


def test_the_version_matches_the_package():
    from vcut import __version__

    data = tomllib.loads(read("pyproject.toml"))
    assert data["project"]["version"] == __version__


def test_both_commands_are_installed():
    data = tomllib.loads(read("pyproject.toml"))
    assert "vcut" in data["project"]["scripts"]
    assert "vcut-gui" in data["project"]["gui-scripts"]


def test_uploading_is_an_optional_extra():
    # Pywikibot is heavy and only needed by people who upload.
    data = tomllib.loads(read("pyproject.toml"))
    assert any("pywikibot" in dep for dep in data["project"]["optional-dependencies"]["upload"])


def test_the_wheel_does_not_double_include_the_logo():
    # A force-include of package data adds the same file twice and the wheel
    # build then fails.
    data = tomllib.loads(read("pyproject.toml"))
    wheel = data.get("tool", {}).get("hatch", {}).get("build", {}).get("targets", {}).get("wheel", {})
    assert "force-include" not in wheel


# -- scripts and docs ------------------------------------------------------


def test_there_is_a_build_script_for_each_platform():
    assert (ROOT / "packaging" / "build-linux.sh").is_file()
    assert (ROOT / "packaging" / "build-windows.ps1").is_file()


def test_the_build_scripts_are_executable():
    import os
    import stat

    mode = (ROOT / "packaging" / "build-linux.sh").stat().st_mode
    assert mode & stat.S_IXUSR, "build-linux.sh is not executable"
    assert os.access(ROOT / "packaging" / "install.sh", os.X_OK)


def test_the_installer_can_undo_itself():
    assert "--uninstall" in read("packaging/install.sh")


def test_the_install_guide_covers_both_platforms():
    guide = read("INSTALL.md")
    assert "### Windows" in guide
    assert "### Linux" in guide
    # FFmpeg is the one thing people have to install themselves.
    assert "winget install" in guide
    assert "apt install ffmpeg" in guide


def test_the_install_guide_says_ffmpeg_is_not_bundled():
    assert "never bundled" in read("INSTALL.md")
