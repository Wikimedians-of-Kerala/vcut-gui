#!/usr/bin/env bash
# Build the Linux package: dist/vcut-gui-linux.tar.gz
#
#     ./packaging/build-linux.sh
#
# FFmpeg is not bundled; see INSTALL.md.
set -euo pipefail

# Report where a failure happened. Without this the script dies silently
# under `set -e` and a CI log ends mid-step with nothing to act on.
trap 'rc=$?; echo "error: ${BASH_SOURCE[0]}:${LINENO} exited ${rc}" >&2; exit $rc' ERR

cd "$(dirname "$0")/.."

# A stale dist/ from an earlier run looks exactly like a fresh build, so
# clear it before anything can fail and leave it behind.
rm -rf build dist/vcut-gui dist/vcut-gui-linux.tar.gz

echo "==> Preparing the build environment"
# Pin the interpreter rather than taking whatever uv finds: a CI image may
# ship several, and the bundle embeds whichever one builds it.
uv venv --quiet --clear --python "${VCUT_PYTHON:-3.12}" .venv-build
uv pip install --quiet --python .venv-build/bin/python -e . pyinstaller

echo "==> Building"
# --log-level WARN keeps CI logs readable; the INFO firehose buries the one
# line that matters. Failures still print in full.
#
# The log is kept because PyInstaller only *warns* about a library it cannot
# resolve, then builds a bundle that dies on import. That cost several CI
# runs with libpulse: it is present on a developer's desktop, so the bundle
# looked fine locally and failed on a bare machine.
build_log=$(mktemp)
trap 'rm -f "$build_log"' EXIT
.venv-build/bin/pyinstaller --noconfirm --clean --log-level WARN vcut-gui.spec \
    2>&1 | tee "$build_log"

if grep -q "Library not found" "$build_log"; then
    echo >&2
    echo "error: PyInstaller could not resolve these libraries:" >&2
    grep -o "could not resolve '[^']*'" "$build_log" | sort -u | sed 's/^/  /' >&2
    echo >&2
    echo "The bundle would start on this machine and fail on one without" >&2
    echo "them. Install the matching -dev or runtime packages and rebuild;" >&2
    echo "see docs/BUILDING.md." >&2
    exit 1
fi

if [ ! -x dist/vcut-gui/vcut-gui ]; then
    echo "error: PyInstaller did not produce dist/vcut-gui/vcut-gui" >&2
    exit 1
fi

echo "==> Checking the bundle starts"
# Catches the entry-point and missing-import faults that only appear once
# the app is running outside a Python environment.
if ! ( cd dist/vcut-gui && env -u VIRTUAL_ENV -u PYTHONPATH \
        QT_QPA_PLATFORM=offscreen timeout 90 ./vcut-gui --self-test ); then
    echo "error: the built application failed to start" >&2
    exit 1
fi

echo "==> Adding the installer and desktop entry"
install -m 755 packaging/install.sh dist/vcut-gui/install.sh
install -m 644 packaging/vcut-gui.desktop dist/vcut-gui/vcut-gui.desktop
install -m 644 src/vcut/gui/logo/vcutcli-logo.svg dist/vcut-gui/vcut-gui.svg
install -m 644 INSTALL.md dist/vcut-gui/INSTALL.md
install -m 644 README.md dist/vcut-gui/README.md

echo "==> Packing"
tar -C dist -czf dist/vcut-gui-linux.tar.gz vcut-gui

echo
echo "Built dist/vcut-gui-linux.tar.gz"
du -h dist/vcut-gui-linux.tar.gz
