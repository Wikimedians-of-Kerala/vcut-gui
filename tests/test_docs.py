"""The shipped documentation.

Documentation goes stale silently: a renamed script or a deleted file leaves
instructions that look fine and do not work. These check the parts that can
be checked.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_the_guides_exist():
    assert (DOCS / "GUIDE.md").is_file()
    assert (DOCS / "BUILDING.md").is_file()


def test_the_build_guide_names_the_real_scripts():
    building = read("docs/BUILDING.md")
    for script in ("packaging/build-linux.sh", "packaging\\build-windows.ps1"):
        assert script in building
    assert (ROOT / "packaging/build-linux.sh").is_file()
    assert (ROOT / "packaging/build-windows.ps1").is_file()


def test_the_build_guide_names_the_real_artifacts():
    # Renaming an output without updating the instructions sends people
    # looking for a file that is not there.
    building = read("docs/BUILDING.md")
    linux = read("packaging/build-linux.sh")
    windows = read("packaging/build-windows.ps1")
    assert "vcut-gui-linux.tar.gz" in building and "vcut-gui-linux.tar.gz" in linux
    assert "vcut-gui-windows.zip" in building and "vcut-gui-windows.zip" in windows


def test_the_build_guide_records_the_webengine_tradeoff():
    # The spec excludes WebEngine, which silently disables browser sign-in in
    # packaged builds. If that exclusion goes, this note should go with it.
    spec = read("vcut-gui.spec")
    building = read("docs/BUILDING.md")
    if "PySide6.QtWebEngineCore" in spec and "excludes" in spec:
        assert "QtWebEngineCore" in building
        assert "browser" in building.lower()


def test_internal_document_links_resolve():
    # A relative link to a file that was moved or never written.
    for doc in sorted(DOCS.glob("*.md")) + [ROOT / "README.md", ROOT / "INSTALL.md"]:
        text = doc.read_text(encoding="utf-8")
        for target in re.findall(r"\]\((?!https?:|#)([^)#]+)", text):
            resolved = (doc.parent / target).resolve()
            assert resolved.exists(), f"{doc.name} -> {target}"


def test_readme_points_at_both_guides():
    readme = read("README.md")
    assert "docs/GUIDE.md" in readme
    assert "docs/BUILDING.md" in readme


# -- project addresses -----------------------------------------------------

REPO = "https://github.com/Wikimedians-of-Kerala/vcut-gui"


def test_no_stale_repository_addresses():
    # The project moved; a leftover address sends people to a repository
    # that is not this one.
    for name in ("README.md", "INSTALL.md", "pyproject.toml",
                 "docs/GUIDE.md", "docs/BUILDING.md",
                 "src/vcut/gui/browser_login.py"):
        text = read(name)
        assert "ranjithsiji" not in text, name
        assert "gitlab.com" not in text, name


def test_the_user_agent_names_this_repository():
    # Wikimedia asks tools to identify themselves, and a wrong address there
    # misidentifies the tool rather than merely being untidy.
    source = read("src/vcut/gui/browser_login.py")
    assert REPO in source


def test_packaging_metadata_points_at_the_repository():
    import tomllib

    data = tomllib.loads(read("pyproject.toml"))
    urls = data["project"]["urls"]
    assert urls["Homepage"] == REPO
    for value in urls.values():
        assert value.startswith(REPO), value


def test_the_guide_does_not_name_a_player_that_is_no_longer_used():
    """Troubleshooting advice must point at the machinery actually in use.

    The guide used to send people to install GStreamer, which was Qt's
    backend. Video is libmpv's job now, so that advice would waste a
    user's time at the moment something is already wrong.
    """
    guide = (DOCS / "GUIDE.md").read_text()
    assert "gstreamer" not in guide.lower()
    assert "libmpv" in guide


def test_the_build_guide_records_the_windows_libmpv_download():
    """A build-time network fetch is not something to discover by surprise.

    The Windows build pulls a 120 MB DLL from a third-party release, which
    a maintainer needs to know about -- for offline builds, and because it
    is a dependency on someone else's release schedule.
    """
    building = (DOCS / "BUILDING.md").read_text()
    assert "libmpv-2.dll" in building
    assert "mpv-winbuild-cmake" in building
    # And why Linux is treated differently.
    assert "libmpv2" in building


def test_the_build_guide_covers_the_distribution_packages():
    """Why no build service is needed is the part worth writing down.

    OBS, Copr and Launchpad exist to compile from source across many
    distribution versions. This bundle carries its own Python and Qt, so
    there is nothing to compile -- and someone reaching for one of those
    would spend a day finding that out.
    """
    building = (DOCS / "BUILDING.md").read_text()
    assert "build-packages.sh" in building
    # The two differ in what they can require, which is easy to get wrong.
    assert "RPM Fusion" in building
    assert "mpv-libs" in building
