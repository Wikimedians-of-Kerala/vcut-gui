#!/usr/bin/env bash
# Install an unpacked vcut-gui into the system, with a menu entry.
#
#     sudo ./install.sh              install
#     sudo ./install.sh --uninstall  remove it again
set -euo pipefail

PREFIX=/opt/vcut-gui
BIN=/usr/local/bin/vcut-gui
DESKTOP=/usr/share/applications/vcut-gui.desktop
ICON=/usr/share/icons/hicolor/scalable/apps/vcut-gui.svg

if [ "${1:-}" = "--uninstall" ]; then
    rm -rf "$PREFIX" "$BIN" "$DESKTOP" "$ICON"
    command -v update-desktop-database >/dev/null && update-desktop-database || true
    echo "Removed vcut-gui."
    exit 0
fi

if [ "$(id -u)" -ne 0 ]; then
    echo "This needs to run with sudo." >&2
    exit 1
fi

here="$(cd "$(dirname "$0")" && pwd)"
if [ ! -x "$here/vcut-gui" ]; then
    echo "vcut-gui is not in $here — unpack the archive first." >&2
    exit 1
fi

echo "Installing to $PREFIX"
rm -rf "$PREFIX"
mkdir -p "$PREFIX"
cp -a "$here/." "$PREFIX/"

ln -sf "$PREFIX/vcut-gui" "$BIN"
install -Dm644 "$here/vcut-gui.desktop" "$DESKTOP"
[ -f "$here/vcut-gui.svg" ] && install -Dm644 "$here/vcut-gui.svg" "$ICON"
command -v update-desktop-database >/dev/null && update-desktop-database || true

echo
echo "Installed. Run it with 'vcut-gui' or from your applications menu."
if ! command -v ffmpeg >/dev/null; then
    echo
    echo "NOTE: FFmpeg is not installed. vcut needs it:"
    echo "  sudo apt install ffmpeg     # or dnf / pacman"
fi
