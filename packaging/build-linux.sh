#!/usr/bin/env bash
# Build the Linux package: dist/vcut-gui-linux.tar.gz
#
#     ./packaging/build-linux.sh
#
# FFmpeg is not bundled; see INSTALL.md.
set -euo pipefail

cd "$(dirname "$0")/.."

# A stale dist/ from an earlier run looks exactly like a fresh build, so
# clear it before anything can fail and leave it behind.
rm -rf build dist/vcut-gui dist/vcut-gui-linux.tar.gz

echo "==> Preparing the build environment"
uv venv --quiet --clear .venv-build
uv pip install --quiet --python .venv-build/bin/python -e . pyinstaller

echo "==> Building"
.venv-build/bin/pyinstaller --noconfirm --clean vcut-gui.spec

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
