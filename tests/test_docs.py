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
