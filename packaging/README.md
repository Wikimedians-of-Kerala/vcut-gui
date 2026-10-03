# Packaging

End-user installation instructions live in [INSTALL.md](../INSTALL.md).
This file is about producing the packages.

## Building

```sh
./packaging/build-linux.sh                                    # Linux
powershell -ExecutionPolicy Bypass -File packaging\build-windows.ps1   # Windows
```

Each produces an archive in `dist/`:

- `dist/vcut-gui-linux.tar.gz`
- `dist/vcut-gui-windows.zip`

PyInstaller does not cross-compile, so each has to be built on its own
platform. The CI workflow in `.github/workflows/release.yml` builds both on
a tag push and attaches them to the release.

Both scripts start the built application with `--self-test` before packing
it. A bundle can build cleanly and still fail at launch — a missing hidden
import, or an entry point whose relative imports no longer resolve — and
that check is what catches it.

## The entry point

The bundle starts at `packaging/entry.py`, not at `src/vcut/gui/app.py`.
PyInstaller runs its entry script as a top-level module, so `app.py`'s
relative imports (`from ..settings import ...`) fail with
"attempted relative import with no known parent package". The wrapper
imports through the installed package name instead.

## FFmpeg

FFmpeg is not bundled: it is large, and which codecs a build carries, under
which licence, varies. The app looks for `ffmpeg` and `ffprobe` on `PATH`
and says so clearly when they are missing.

To ship it anyway, copy `ffmpeg` and `ffprobe` (with `.exe` on Windows) into
`dist/vcut-gui/` beside the executable; they are found there first.

## Wheels

```sh
uv build
```

Produces both a wheel and an sdist in `dist/`. The logo ships as package
data — do not add a `force-include` for it, which would add the same file
twice and fail the wheel build.

## Windows notes

- Build on Windows; there is no cross-compilation.
- Unsigned executables draw a SmartScreen warning on first run. Signing
  needs a certificate, which this project does not have.
