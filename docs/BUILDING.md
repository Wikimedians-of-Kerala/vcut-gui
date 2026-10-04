# Building vcut for Linux and Windows

How to produce the downloadable packages — the Linux tarball and the Windows
zip — that run without Python installed.

If you only want to *use* the program, you do not need this file. Install a
ready-made package instead: [INSTALL.md](../INSTALL.md).

## Contents

- [What gets built](#what-gets-built)
- [Before you build](#before-you-build)
- [Building on Linux](#building-on-linux)
- [Building on Windows](#building-on-windows)
- [Building both with CI](#building-both-with-ci)
- [Building the wheel](#building-the-wheel)
- [What is inside the bundle](#what-is-inside-the-bundle)
- [Cutting a release](#cutting-a-release)
- [When a build fails](#when-a-build-fails)

---

## What gets built

| Command | Produces | Runs on |
| --- | --- | --- |
| `./packaging/build-linux.sh` | `dist/vcut-gui-linux.tar.gz` | Linux, no Python needed |
| `packaging\build-windows.ps1` | `dist\vcut-gui-windows.zip` | Windows, no Python needed |
| `uv build` | `dist/*.whl` and `dist/*.tar.gz` | Anywhere with Python 3.11+ |

**PyInstaller does not cross-compile.** The Windows package must be built on
Windows and the Linux package on Linux. There is no flag for this and no way
around it; if you only have one of the two machines, use
[CI](#building-both-with-ci), which has both.

---

## Before you build

You need **Python 3.11 or newer** and **[uv](https://docs.astral.sh/uv/)**.
Both build scripts create their own throwaway environment in `.venv-build/`
and install PyInstaller into it, so nothing is required globally beyond those
two.

You do **not** need FFmpeg to build. It is not bundled — see
[FFmpeg is not included](#ffmpeg-is-not-included).

Check uv is present:

```sh
uv --version
```

---

## Building on Linux

```sh
./packaging/build-linux.sh
```

That runs seven steps, and prints each as it goes:

1. **Clears `build/` and `dist/vcut-gui/`.** A stale directory from an earlier
   run looks exactly like a fresh build, so it goes first — before anything
   can fail and leave it behind.
2. **Creates `.venv-build/`** and installs the project plus PyInstaller.
3. **Runs PyInstaller** against `vcut-gui.spec`.
4. **Checks PyInstaller actually produced the executable.**
5. **Starts the built application** with `--self-test`, under
   `QT_QPA_PLATFORM=offscreen` so it needs no display.
6. **Adds** `install.sh`, the desktop entry, the logo and the documentation.
7. **Packs** the tarball.

Step 5 is the one that earns its keep. A bundle can build perfectly and still
fail the moment you launch it — a hidden import PyInstaller did not trace, or
an entry point whose relative imports no longer resolve outside a package.
The self-test runs the real startup path and catches both. It is also why the
build takes a little longer than it looks like it should.

### Build dependencies on a bare machine

A minimal Linux install — a container, or a CI runner — may lack the Qt
runtime libraries. On Debian or Ubuntu:

```sh
sudo apt-get install -y libegl1 libgl1 libxkbcommon-x11-0 \
  libxcb-cursor0 libxcb-icccm4 libxcb-keysyms1 libxcb-shape0
```

These are what the CI workflow installs. On a normal desktop they are already
there.

### Testing what you built

```sh
cd dist/vcut-gui
./vcut-gui
```

To test the system-wide installation too:

```sh
sudo ./install.sh              # into /opt/vcut-gui, with a menu entry
sudo ./install.sh --uninstall  # and back out again
```

---

## Building on Windows

In PowerShell, from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build-windows.ps1
```

`-ExecutionPolicy Bypass` is needed because Windows refuses to run unsigned
scripts by default. It applies to that one invocation only and changes nothing
on the machine.

The steps mirror the Linux script, including the `--self-test` launch, and the
result is `dist\vcut-gui-windows.zip`.

### Testing what you built

Unpack the zip somewhere and run `vcut-gui.exe`. Test from an **unpacked**
folder, not from inside the archive viewer — Windows will happily run an
executable from a zip preview, where it cannot find the files beside it, and
the failure looks like a bug in the application.

### The SmartScreen warning

The executable is unsigned, so the first run shows *"Windows protected your
PC"*. **More info → Run anyway** gets past it.

Removing that warning needs a code-signing certificate from a commercial
authority, which this project does not have. It is worth telling users about
in release notes, because an unexplained SmartScreen warning is exactly what a
careful person refuses to click through.

---

## Building both with CI

`.github/workflows/release.yml` builds all three artifacts — Linux, Windows
and the wheel — on GitHub's runners. This is the practical answer to
PyInstaller's lack of cross-compilation.

It runs when you **push a version tag**:

```sh
git tag -a v1.0.3 -m "Release 1.0.3"
git push origin v1.0.3
```

and attaches the artifacts to the GitHub release.

You can also run it by hand from the Actions tab (**Run workflow**) to check
packaging still works without cutting a release. Doing that after any change
to dependencies or to the spec file is cheaper than discovering the breakage
at release time.

> **Note** — the artifacts are only attached to a release for a tag push.
> A manual run uploads them as workflow artifacts instead.

---

## Building the wheel

```sh
uv build
```

Produces a wheel and an sdist in `dist/`. These are what `pip install` and
`pipx install` consume, and they need no PyInstaller.

Two packaging traps, both of which have already bitten this project:

**Do not add a `force-include` for the logo.** It ships as package data
already, and including it twice fails the wheel build with *"a second file is
being added to the wheel archive at the same path"*.

**Keep `.venv-build/` out of the sdist.** A build environment contains
absolute symlinks, and the sdist build refuses them outright. It is excluded
in `pyproject.toml` and listed in `.gitignore`, and there are tests guarding
both; if you add another build directory, exclude it the same way.

---

## What is inside the bundle

PyInstaller produces a **one-folder** application, not a single file: the
executable sits beside the Python runtime, the Qt libraries and the program's
own files. Starting is faster than a one-file bundle, which has to unpack
itself to a temporary directory on every launch.

### The entry point

The bundle starts at `packaging/entry.py`, **not** at `src/vcut/gui/app.py`.

PyInstaller runs its entry script as a top-level module, so `app.py`'s
relative imports (`from ..settings import ...`) fail with *"attempted relative
import with no known parent package"*. The wrapper imports through the
installed package name instead, which resolves properly.

### FFmpeg is not included

FFmpeg is large, and which codecs a given build carries — and under which
licence — varies considerably. Bundling it would mean choosing one build for
everyone and taking on its licensing.

So the application looks for `ffmpeg` and `ffprobe` on `PATH` and says
clearly, with installation instructions, when they are missing.

To ship it anyway, copy `ffmpeg` and `ffprobe` (with `.exe` on Windows) into
`dist/vcut-gui/` beside the executable. They are found there before `PATH`.

### What is deliberately left out

`vcut-gui.spec` excludes several packages to keep the download reasonable:

| Excluded | Consequence |
| --- | --- |
| `tkinter`, `matplotlib`, `numpy` | None — pulled in indirectly, never used. |
| Qt WebEngine | **Browser sign-in is unavailable in packaged builds.** |
| Pywikibot | Not bundled; the upload screen explains how to install it. |

The WebEngine exclusion is a real trade-off, and getting it *half* right is
worse than either answer — which is what happened here, so it is worth
reading before you change it.

Qt WebEngine is an embedded Chromium: roughly 150 MB, more than the whole
rest of the bundle. Excluding it keeps the download reasonable. But browser
sign-in is how users with a **passkey or two-factor account** log in, because
a passkey is bound to the browser origin and cannot be typed into a desktop
form.

### Why it takes more than one exclusion

Excluding `PySide6.QtWebEngineCore` on its own does **not** remove WebEngine.
It stops PyInstaller's hook collecting Chromium's resource files — the
`.pak` archives, `icudtl.dat`, the `QtWebEngineProcess` helper — while the
shared libraries still arrive as transitive dependencies of Qt libraries that
are genuinely needed.

The result is the worst of both: the build carries `libQt6WebEngineCore.so`
and friends, and `PySide6.QtWebEngineWidgets` still imports, so the
application's `webengine_available()` check reports **True** and the login
window offers a browser that cannot start.

Measured on this project, that mistake cost **119 MB of the compressed
download** — 222 MB against 103 MB, or 578 MB against 264 MB unpacked — for
a feature that did not work.

So the spec does two things: excludes `QtWebEngineCore`, `QtWebEngineWidgets`
and `QtWebEngineQuick`, and then filters the leftover shared libraries out of
`a.binaries` and `a.datas` by name. With both in place the module genuinely
is not importable, the availability check returns False, and the login window
says *"This build has no embedded browser, so signing in this way is
unavailable. Use a bot password instead."* Bot passwords work for every
account, so nobody is locked out — but a passkey user has to create one.

Two tests in `tests/test_packaging.py` guard this, because the failure is
silent: a build with half-excluded WebEngine looks fine and passes its
self-test.

### Including it instead

Remove the three `PySide6.QtWebEngine*` entries from `excludes`, delete the
`a.binaries` / `a.datas` filter below them, and add
`PySide6.QtWebEngineWidgets` to `hiddenimports`. Then **check the resource
files actually arrived**, because their absence is what made the half-state
so hard to spot:

```sh
find dist/vcut-gui -name '*.pak' | wc -l      # should be dozens, not 0
find dist/vcut-gui -name 'QtWebEngineProcess*' # should exist
```

Expect the package to roughly double. Shipping both a slim and a full build
is the other option, at the cost of explaining the difference on the
downloads page.

### Application icons

`icon=None` in the spec, so the executable carries PyInstaller's default.

To change that you need a `.ico` for Windows and a `.icns` for macOS,
converted from `src/vcut/gui/logo/vcutcli-logo.svg`:

```sh
# Windows .ico, with ImageMagick
magick -background none vcutcli-logo.svg -define icon:auto-resize=256,128,64,48,32,16 vcut-gui.ico
```

Then set `icon="vcut-gui.ico"` in the `EXE()` block. The *window* icon already
comes from the SVG at runtime; this is only the file icon in Explorer.

---

## Cutting a release

1. Update `CHANGELOG.md` — move the Unreleased entries under the new version.
2. Bump the version in `pyproject.toml` and `src/vcut/__init__.py`.
3. Run the tests: `uv run pytest`.
4. Commit.
5. Tag and push:

   ```sh
   git tag -a v1.0.3 -m "Release 1.0.3"
   git push origin master
   git push origin v1.0.3
   ```

CI builds all three packages and attaches them to the release.

> **The tag has to be pushed separately.** `git push` alone does not push
> tags, so the workflow never fires and no release appears. This is the most
> common way a release silently does not happen.

---

## When a build fails

**`uv: command not found`** — install uv:
`curl -LsSf https://astral.sh/uv/install.sh | sh`, or on Windows
`powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`.

**"the built application failed to start"** — the bundle built but will not
run. Usually a missing hidden import. Find the real error by running it
yourself:

```sh
cd dist/vcut-gui && ./vcut-gui --self-test
```

A `ModuleNotFoundError` names the module to add to `hiddenimports` in
`vcut-gui.spec`. This is common after adding a dependency that is imported
lazily, since PyInstaller cannot see an import that only happens at runtime.

**"attempted relative import with no known parent package"** — something is
entering through `app.py` rather than `packaging/entry.py`. Check the
`Analysis()` entry in the spec.

**The build works locally but fails in CI** — usually a missing system
library, since a runner is barer than a desktop. Check the Qt runtime list
[above](#build-dependencies-on-a-bare-machine) against the workflow.

**"a second file is being added to the wheel archive at the same path"** —
something is included twice. See [the wheel section](#building-the-wheel).

**"symlink path ... is absolute"** on `uv build` — a build environment is
being swept into the sdist. Make sure `.venv-build/` is excluded in
`pyproject.toml`.

**The Windows build cannot find `uv`** — install it in the same PowerShell
session you build from, and reopen PowerShell afterwards so `PATH` updates.

**A stale build keeps reappearing** — both scripts clear `build/` and
`dist/vcut-gui/` at the start, but if you interrupted one mid-run, remove
them by hand and start again.
