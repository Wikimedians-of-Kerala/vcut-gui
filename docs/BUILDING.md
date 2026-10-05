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
| `./packaging/build-packages.sh` | `dist/*.deb` and `dist/*.rpm` | Linux, after the above |
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
  libxcb-cursor0 libxcb-icccm4 libxcb-keysyms1 libxcb-shape0 libmpv2
```

`libmpv2` is what shows the video while cut points are chosen: Qt's bundled
FFmpeg has no AV1 decoder, so without it an AV1 recording plays as a black
rectangle. The video is drawn through the GL context of the widget it sits
in, so it stays inside the window on Wayland as well as X11 — no XWayland,
and no separate player window.

These are what the CI workflow installs. On a normal desktop they are already
there.

### Building a .deb and an .rpm

**CI does this on every release**, in the same job that builds the tarball —
there is nothing to do by hand and no external service involved. What
follows is for building them locally.

After `build-linux.sh`, and on a machine with `dpkg-deb` and `rpmbuild`:

```sh
./packaging/build-packages.sh
```

This produces `dist/vcut-gui_<version>_amd64.deb` and
`dist/vcut-gui-<version>-1.x86_64.rpm`, both around 100 MB.

**Nothing is compiled.** PyInstaller has already embedded Python and Qt, so
the packages carry that directory and the handful of files `install.sh` would
otherwise place by hand: `/opt/vcut-gui`, a symlink at `/usr/bin/vcut-gui`,
the menu entry and the icon. That is why no distribution build service —
OBS, Copr, Launchpad — is needed. Those exist to compile from source across
many distribution versions, and there is no source here to compile.

The two differ in what they require:

| | `.deb` | `.rpm` |
| --- | --- | --- |
| FFmpeg | `ffmpeg` | *not required* |
| libmpv | `libmpv2 \| libmpv1` | `mpv-libs` |

FFmpeg is deliberately absent from the `.rpm`: it is not in Fedora's own
repositories — it comes from RPM Fusion — so requiring it would make the
package refuse to install on a stock system. The program already detects a
missing FFmpeg and says how to install it, which is a better failure than an
uninstallable package.

`AutoReqProv: no` is set for the same class of reason. Left on, `rpmbuild`
reads every bundled library and demands the system provide them all, which
is precisely what a self-contained bundle exists to avoid.

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

### libmpv is downloaded during the build

Windows has no package to depend on for libmpv, so the build fetches it:
`libmpv-2.dll` from the latest [mpv-winbuild-cmake][mpvwin] release, extracted
with 7-Zip and copied in beside the executable. It adds about 120 MB to the
unpacked bundle.

[mpvwin]: https://github.com/shinchiro/mpv-winbuild-cmake/releases

Two consequences worth knowing:

- **The Windows build needs a network connection.** The Linux build does not.
  If the DLL is already in `dist\vcut-gui\`, the step is skipped, so a
  rebuild is offline.
- **The build fails rather than shipping without it.** A bundle missing the
  DLL would start, look correct, and show a black rectangle for AV1 — the
  format this program recommends for Commons. The release workflow checks the
  archive for it as well.

Qt alone cannot decode AV1: its bundled FFmpeg has no AV1 decoder compiled in.
The program puts its own directory on `PATH` before importing python-mpv,
which is how the shipped DLL is found at all — Windows does not search the
program's own folder for it otherwise.

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
PyInstaller's lack of cross-compilation: you almost certainly do not have
both machines, and GitHub does.

### Why GitHub and not GitLab

The project is on GitHub specifically because of the Windows build.

| | Linux runners | Windows runners |
| --- | --- | --- |
| GitHub Actions, public repository | Free | **Free** |
| GitHub Actions, private repository | 2,000 min/month | Free minutes count **double** |
| GitLab CI, free tier | 400 min/month | **None** |

GitLab's free tier has no Windows shared runners at all — producing a
`.exe` there means registering and maintaining a Windows machine of your
own as a runner. For a volunteer project that is a standing cost for one
build artifact, so GitHub it is.

This matters only for the `.exe`. If you ever move the project, the Linux
package and the wheel build anywhere; the Windows job is the part that needs
a host offering free Windows runners.

### Setting it up

There is nothing to install and no secret to configure. The workflow file is
already in the repository, and GitHub picks it up on its own:

1. **Push the repository to GitHub**, if it is not there yet. The workflow
   appears under the **Actions** tab within a minute.
2. **Make sure Actions is enabled.** On a fresh repository it usually is;
   on a fork it has to be switched on. *Settings → Actions → General →
   Allow all actions*.
3. **Check the workflow may write releases.** *Settings → Actions → General
   → Workflow permissions* must be **Read and write**, or the release job
   cannot attach the packages. The workflow asks for `contents: write`
   itself, but the repository setting can still override it.
4. **Keep the repository public** if you want the Windows build to stay
   free. Private repositories bill Windows minutes at double rate against
   a 2,000-minute monthly allowance.

The `GITHUB_TOKEN` the release job uses is provided automatically. You do
not create it, and there is no secret to paste anywhere.

### Where the packages appear

A tag publishes them to the **Releases** page. Every other run keeps them as
workflow artifacts instead, which are easy to miss:

1. **Actions** tab.
2. Click the run — it must be a **Build release packages** run, not a
   **Tests** run.
3. Scroll to the bottom — **Artifacts**.

There you will find `vcut-gui-linux`, `vcut-gui-packages`,
`vcut-gui-windows` and `vcut-gui-wheel`, each a zip around the package.
GitHub always wraps artifacts in a zip, so the Linux one downloads as a zip
containing the `.tar.gz`, and the Windows one a zip inside a zip.
`vcut-gui-packages` holds the `.deb` and the `.rpm`.

Artifacts expire after 90 days; releases do not.

> **No Artifacts section?** Then that run built nothing, and there are only
> two ways that happens.
>
> **You are looking at a Tests run.** Tests never produces artifacts — it
> only runs the suite. Check the workflow name at the top of the page.
>
> **The build was skipped.** Build release packages only runs for a tag, a
> change under `packaging/` or to the spec or dependencies, or a manual
> run. A commit touching only `src/` or `tests/` does not build, by
> design — see [When it runs](#when-it-runs) — so there is nothing to
> download.
>
> Either way the fix is the same: **Actions → Build release packages →
> Run workflow**. It needs no commit.

### When it runs

| Trigger | Builds | Publishes |
| --- | --- | --- |
| A `v*` tag | Yes | **Yes** — a GitHub release |
| A push or PR touching packaging | Yes | No — artifacts only |
| **Run workflow** by hand | Yes | No — artifacts only |
| An ordinary commit | No | No |

Packaging changes — the spec, the build scripts, the dependencies — build on
every push and pull request, because a broken spec otherwise stays hidden
until a tag, which is the worst moment to find it. Ordinary commits do not
trigger a build, so the Windows minutes go on changes that could actually
affect packaging.

### Trying it before you tag

Run it by hand first — **Actions → Build release packages → Run workflow**.
That runs the tests and both builds, uploads the packages as workflow
artifacts, and skips the release job, so you can download and try the
`.exe` without publishing anything. Doing this once before the first real
tag is worth the ten minutes.

### Two workflows, not one

```
Tests (tests.yml)              Build release packages (release.yml)
  every push and PR              tags, and packaging changes
  Linux + Windows                  linux  ──┐
  Python 3.11 and 3.13             windows ─┼── release  (tags only)
                                   wheel  ──┘
```

**The builds do not re-run the suite.** Tests already runs it on every push
across both platforms and two Python versions; repeating it in the build
workflow would double every push's CI for no extra signal — and did, until
these were split.

A tag still must not publish broken code, so the release job checks that
Tests *concluded successfully for the commit being tagged* before attaching
anything. It reads the result rather than recomputing it.

**This is why you push the commit before tagging it.** Tag a commit that
master has never seen and there is no Tests result to find, so the release
job stops with "Tests did not pass (got: missing)". Nothing is published;
push the branch, let Tests finish, then push the tag.

Each build checks its own archive before uploading: that the file exists,
that it unpacks, that the executable is inside, and that Qt WebEngine has
not crept back in — the fault described above, which doubles the download
for a browser that cannot start.

The wheel is checked with `twine check`, because broken metadata installs
fine locally and fails on PyPI.

### It runs when you push a version tag

```sh
git tag -a v1.0.3 -m "Release 1.0.3"
git push origin v1.0.3
```

Ten minutes or so later the release is on the Releases page with all three
packages attached.

> **The artifacts are only attached to a release for a tag push.** A manual
> run uploads them as workflow artifacts instead, which is what makes it
> safe to use as a rehearsal.

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

### libmpv is included on Windows, but not on Linux

The opposite of FFmpeg's treatment, for a plain reason: Linux distributions
package libmpv (`libmpv2` on Debian and Ubuntu), and Windows has nothing to
depend on. A Windows user with no DLL has no reasonable way to fix it, so the
build fetches one; a Linux user installs a package.

Nothing is lost when it is absent. The program falls back to Qt's player,
which shows every format except AV1, and says which one is in use under
*Help > About*.

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
4. Commit, and **push to master**. Wait for Tests to go green — the release
   job looks for that result and refuses to publish without it.
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
