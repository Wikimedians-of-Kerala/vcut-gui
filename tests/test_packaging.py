"""The packaging configuration.

These catch the mistakes that only show up in a built package, where a full
PyInstaller run takes minutes.
"""

import tomllib
from pathlib import Path

import pytest

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


def test_the_sdist_excludes_build_environments():
    # A virtual environment cannot go into an sdist: its absolute symlinks
    # make the tar unusable, and the packaging scripts leave one behind.
    data = tomllib.loads(read("pyproject.toml"))
    sdist = data["tool"]["hatch"]["build"]["targets"]["sdist"]
    assert ".venv-build" in sdist["exclude"]
    assert ".venv" in sdist["exclude"]


def test_build_environments_are_not_committed():
    ignored = read(".gitignore").splitlines()
    assert ".venv/" in ignored
    assert ".venv-build/" in ignored


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
    """The shell scripts must be executable for whoever clones the project.

    Checked against the git index rather than the filesystem: Windows has
    no POSIX permission bits, so a checkout there reports 0o666 whatever
    the repository says. The index mode is what every clone gets, which
    makes it both the honest fact and the portable one.
    """
    import subprocess

    listing = subprocess.run(
        ["git", "ls-files", "-s", "--", "packaging"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout

    modes = {}
    for line in listing.splitlines():
        meta, _, path = line.partition("\t")
        modes[path] = meta.split()[0]

    for script in ("packaging/build-linux.sh", "packaging/install.sh"):
        assert modes.get(script) == "100755", f"{script} is {modes.get(script)}"


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


# -- Qt WebEngine ----------------------------------------------------------


def test_webengine_is_excluded_completely():
    # Excluding QtWebEngineCore alone stops its hook collecting Chromium's
    # .pak resources, but the shared libraries still arrive as transitive
    # dependencies. The result carries ~150 MB of Chromium that cannot start
    # while webengine_available() still reports True, so the login window
    # offers a browser that then fails. Both modules have to go.
    spec = read("vcut-gui.spec")
    for module in ("PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets"):
        assert module in spec, module


def test_webengine_binaries_are_pruned():
    # The excludes alone do not remove the shared libraries; the spec filters
    # them out of a.binaries and a.datas by name.
    spec = read("vcut-gui.spec")
    assert "a.binaries = [" in spec
    assert "a.datas = [" in spec
    assert "qt6webengine" in spec.lower()
    # TOC is deprecated in PyInstaller 6 and only reaches a spec as an
    # injected global; plain lists do the same job without that dependency.
    # Checked against code lines, since the comment above mentions it.
    code = [line for line in spec.splitlines() if not line.lstrip().startswith("#")]
    assert not any("TOC(" in line for line in code)


def test_the_app_detects_a_missing_webengine_rather_than_assuming():
    # Without this check the packaged build would offer browser sign-in and
    # fail when it was used.
    source = read("src/vcut/gui/browser_login.py")
    assert "def webengine_available" in source
    login = read("src/vcut/gui/login_dialog.py")
    assert "webengine_available()" in login


# -- the release workflow --------------------------------------------------


def _release_workflow() -> dict:
    # Skip rather than error if PyYAML is absent: a check that cannot run is
    # not the same as a product fault, and this file is otherwise importable
    # with nothing but the standard library.
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load(read(".github/workflows/release.yml"))


def test_a_tag_cannot_release_without_passing_tests():
    """Without a gate a red suite still produces a release, and the first
    anyone knows of it is a broken download.

    The suite is not re-run in this workflow -- Tests already covers every
    push on a wider matrix, and repeating it would double each push's CI
    for no extra signal. Instead the release job checks that Tests
    concluded successfully for the commit being tagged.
    """
    release = _release_workflow()["jobs"]["release"]
    steps = " ".join(str(step) for step in release["steps"])
    assert "gh run list" in steps and "--workflow Tests" in steps, (
        "the release job does not check the Tests result"
    )
    assert "conclusion" in steps


def test_the_tests_workflow_covers_every_push():
    # The release gate above is only meaningful if Tests actually runs.
    import yaml

    tests = yaml.safe_load(read(".github/workflows/tests.yml"))
    triggers = tests.get("on", tests.get(True))
    assert "push" in triggers and "pull_request" in triggers
    matrix = tests["jobs"]["test"]["strategy"]["matrix"]
    assert any("windows" in os for os in matrix["os"])
    assert any("ubuntu" in os for os in matrix["os"])


def test_the_workflows_do_not_both_run_the_suite():
    # Two workflows running pytest on every push doubles CI for no signal,
    # and produced two runs per push until this was split.
    release = read(".github/workflows/release.yml")
    assert "pytest" not in release, "the release workflow re-runs the tests"


def test_the_release_waits_for_every_package():
    needs = _release_workflow()["jobs"]["release"]["needs"]
    assert set(needs) == {"linux", "windows", "wheel"}


def test_both_platforms_are_built():
    jobs = _release_workflow()["jobs"]
    assert jobs["linux"]["runs-on"].startswith("ubuntu")
    assert jobs["windows"]["runs-on"].startswith("windows")


def test_missing_artifacts_fail_rather_than_release_nothing():
    # upload-artifact is silent by default when it finds no files, which
    # would publish a release with pieces quietly missing.
    workflow = read(".github/workflows/release.yml")
    assert workflow.count("if-no-files-found: error") == 3


def test_packaging_changes_are_built_not_only_tags():
    # A broken spec otherwise stays hidden until a tag, which is the worst
    # moment to discover it.
    triggers = _release_workflow()
    on = triggers.get("on", triggers.get(True))
    assert "pull_request" in on
    watched = set(on["push"].get("paths", []))
    assert "vcut-gui.spec" in watched
    assert any(path.startswith("packaging/") for path in watched)


def test_only_tags_publish_a_release():
    # Building on every packaging push is fine; publishing on one is not.
    gate = _release_workflow()["jobs"]["release"]["if"]
    assert "refs/tags/v" in gate


def test_the_qt_libraries_still_exist_on_the_runner():
    # libgl1-mesa-glx was removed in Ubuntu 24.04, which ubuntu-latest now
    # is; installing it fails the job outright.
    workflow = read(".github/workflows/release.yml")
    assert "libgl1-mesa-glx" not in workflow
    assert "libgl1" in workflow


def test_the_windows_self_test_waits_for_the_app():
    # console=False makes a GUI-subsystem binary, which PowerShell does not
    # wait for: the call operator would read $LASTEXITCODE before the app
    # had finished, so a broken bundle could pass its own check.
    script = read("packaging/build-windows.ps1")
    assert "Start-Process" in script
    assert "-Wait" in script
    assert "--self-test" in script


def test_actions_are_not_on_deprecated_node():
    # GitHub is forcing Node 20 actions onto Node 24; these are the versions
    # that target it natively.
    for name in (".github/workflows/release.yml", ".github/workflows/tests.yml"):
        workflow = read(name)
        assert "actions/checkout@v4" not in workflow, name
        assert "actions/upload-artifact@v4" not in workflow, name
        for stale in ("astral-sh/setup-uv@v5", "astral-sh/setup-uv@v6"):
            assert stale not in workflow, f"{name}: {stale}"
        # setup-uv publishes moving major tags only up to v7; v8 and later
        # exist as exact versions, so "@v10" is a 404 and fails the job
        # before anything runs.
        assert "astral-sh/setup-uv@v10\n" not in workflow, name
        assert "astral-sh/setup-uv@v8\n" not in workflow, name
        assert "astral-sh/setup-uv@v9\n" not in workflow, name


def test_the_version_is_declared_once_and_agrees():
    # Two places hold it; a release where they disagree ships a wheel
    # labelled differently from the application's own About box.
    import tomllib

    declared = tomllib.loads(read("pyproject.toml"))["project"]["version"]
    module = read("src/vcut/__init__.py")
    assert f'__version__ = "{declared}"' in module, module
    # And the changelog should have an entry for it.
    assert f"## {declared}" in read("CHANGELOG.md")


def test_the_tests_only_import_declared_dependencies():
    """A test importing something undeclared passes for whoever happens to
    have it installed and fails in CI. That is how pyyaml slipped in."""
    import ast
    import sys

    data = tomllib.loads(read("pyproject.toml"))["project"]
    distributions = data["dependencies"] + data["optional-dependencies"]["dev"]
    names = {
        dist.split(">")[0].split("=")[0].split("[")[0].strip().lower()
        for dist in distributions
    }
    # A few distributions install under a different import name.
    names |= {"yaml"} if "pyyaml" in names else set()
    names |= {"pytest_cov"} if "pytest-cov" in names else set()

    stdlib = set(sys.stdlib_module_names)
    undeclared: dict[str, set[str]] = {}
    for path in sorted((ROOT / "tests").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            module = None
            if isinstance(node, ast.Import):
                module = node.names[0].name.split(".")[0]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                module = node.module.split(".")[0]
            if not module or module in stdlib or module == "vcut":
                continue
            if module.lower() not in names:
                undeclared.setdefault(module, set()).add(path.name)

    assert not undeclared, f"undeclared test imports: {undeclared}"


def test_every_action_reference_looks_resolvable():
    """A tag that does not exist fails the job before a single step runs,
    and the error names only the action. These are the forms that exist."""
    import re

    known = {
        "actions/checkout": {"v4", "v5"},
        "actions/upload-artifact": {"v4", "v5"},
        "actions/download-artifact": {"v4", "v5", "v6"},
        "softprops/action-gh-release": {"v1", "v2"},
    }
    exact = re.compile(r"^v\d+\.\d+\.\d+$")

    for name in (".github/workflows/release.yml", ".github/workflows/tests.yml"):
        for ref in re.findall(r"uses:\s*(\S+)", read(name)):
            repo, _, tag = ref.partition("@")
            assert tag, f"{name}: {ref} is unpinned"
            if repo in known:
                assert tag in known[repo], f"{name}: unknown tag {ref}"
            else:
                # Anything else must be pinned to an exact version, since a
                # moving major tag may simply not be published.
                assert exact.match(tag), f"{name}: {ref} should pin an exact version"


def test_the_build_script_reports_where_it_failed():
    # Under `set -e` a failing command exits silently, and a CI log then
    # ends mid-step with nothing to act on -- which cost three runs.
    script = read("packaging/build-linux.sh")
    assert "trap" in script and "ERR" in script
    assert "BASH_SOURCE" in script and "LINENO" in script


def test_a_rerun_cannot_cancel_itself():
    # A concurrency group keyed only on the ref makes a re-run of a push
    # share the group with the run it repeats.
    workflow = read(".github/workflows/release.yml")
    group = next(
        line for line in workflow.splitlines() if line.strip().startswith("group:")
    )
    assert "github.run_id" in group, group
