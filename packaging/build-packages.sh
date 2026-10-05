#!/usr/bin/env bash
# Build dist/vcut-gui_<version>_amd64.deb and dist/vcut-gui-<version>-1.x86_64.rpm
#
#     ./packaging/build-packages.sh
#
# Run build-linux.sh first: this packages the bundle that produces, rather
# than building it again.
#
# Nothing is compiled here. PyInstaller has already embedded Python and Qt,
# so these packages only carry that directory and the few things install.sh
# would have put in place -- which is why no distro-specific build service
# is needed, and why the same bundle can go into both formats.
set -euo pipefail

trap 'rc=$?; echo "error: ${BASH_SOURCE[0]}:${LINENO} exited ${rc}" >&2; exit $rc' ERR

cd "$(dirname "$0")/.."

BUNDLE=dist/vcut-gui
if [ ! -x "$BUNDLE/vcut-gui" ]; then
    echo "error: $BUNDLE/vcut-gui is not there — run ./packaging/build-linux.sh first" >&2
    exit 1
fi

# The one source of truth for the version, so a package can never claim a
# different one from the program inside it.
VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' src/vcut/__init__.py)
if [ -z "$VERSION" ]; then
    echo "error: could not read __version__ from src/vcut/__init__.py" >&2
    exit 1
fi
echo "==> Packaging vcut-gui $VERSION"

# Where the files go. /opt is the conventional home for a self-contained
# application that brings its own libraries, which is exactly what this is:
# its Qt and Python must not be mistaken for the system's.
PREFIX=/opt/vcut-gui

# ---------------------------------------------------------------------------
# A staging tree both formats are built from, laid out as it will be installed
# ---------------------------------------------------------------------------
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT

mkdir -p "$STAGE$PREFIX" \
         "$STAGE/usr/bin" \
         "$STAGE/usr/share/applications" \
         "$STAGE/usr/share/icons/hicolor/scalable/apps" \
         "$STAGE/usr/share/doc/vcut-gui"

cp -a "$BUNDLE/." "$STAGE$PREFIX/"
# install.sh belongs to the tarball, where someone unpacks and runs it by
# hand. A package manager does that job itself, and leaving it behind invites
# someone to run both.
rm -f "$STAGE$PREFIX/install.sh"

ln -s "$PREFIX/vcut-gui" "$STAGE/usr/bin/vcut-gui"
install -m 644 packaging/vcut-gui.desktop "$STAGE/usr/share/applications/vcut-gui.desktop"
install -m 644 src/vcut/gui/logo/vcutcli-logo.svg \
    "$STAGE/usr/share/icons/hicolor/scalable/apps/vcut-gui.svg"
install -m 644 README.md INSTALL.md "$STAGE/usr/share/doc/vcut-gui/"

SUMMARY="Cut conference recordings into per-session clips"
DESCRIPTION="Cuts long conference recordings into per-session clips, fetches each
session's details from an Eventyay/pretalx schedule, writes Wikimedia
Commons descriptions, and uploads them."

# ---------------------------------------------------------------------------
# .deb
# ---------------------------------------------------------------------------
echo "==> Building the .deb"
DEB_ROOT="$STAGE/../deb-$$"
rm -rf "$DEB_ROOT"
mkdir -p "$DEB_ROOT/DEBIAN"
cp -a "$STAGE"/. "$DEB_ROOT/"
rm -rf "$DEB_ROOT/DEBIAN" && mkdir -p "$DEB_ROOT/DEBIAN"

# Installed-Size is in kibibytes, and apt shows it before downloading.
INSTALLED_KB=$(du -sk "$STAGE" | cut -f1)

cat > "$DEB_ROOT/DEBIAN/control" <<EOF
Package: vcut-gui
Version: $VERSION
Section: video
Priority: optional
Architecture: amd64
Installed-Size: $INSTALLED_KB
Depends: ffmpeg, libmpv2 | libmpv1
Maintainer: Wikimedians of Kerala <https://github.com/Wikimedians-of-Kerala>
Homepage: https://github.com/Wikimedians-of-Kerala/vcut-gui
Description: $SUMMARY
$(echo "$DESCRIPTION" | sed 's/^/ /;s/^ $/ ./')
EOF

# Refresh the desktop database so the menu entry appears without a log-out.
# Both scripts tolerate the command being absent: a minimal install may not
# have it, and a package must not fail to install over a menu cache.
cat > "$DEB_ROOT/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi
EOF
cat > "$DEB_ROOT/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi
EOF
chmod 755 "$DEB_ROOT/DEBIAN/postinst" "$DEB_ROOT/DEBIAN/postrm"

DEB="dist/vcut-gui_${VERSION}_amd64.deb"
rm -f "$DEB"
# --root-owner-group: without it the package records the building user's
# uid, and the files land owned by whatever account shares that number.
dpkg-deb --build --root-owner-group "$DEB_ROOT" "$DEB" >/dev/null
rm -rf "$DEB_ROOT"

# ---------------------------------------------------------------------------
# .rpm
# ---------------------------------------------------------------------------
echo "==> Building the .rpm"
RPM_TOP="$STAGE/../rpm-$$"
rm -rf "$RPM_TOP"
mkdir -p "$RPM_TOP"/{BUILD,RPMS,SPECS,BUILDROOT}

# No ffmpeg dependency on purpose. It is not in Fedora's own repositories --
# it needs RPM Fusion -- so requiring it would make the package refuse to
# install on a stock system. The program already detects a missing FFmpeg and
# says how to install it, which is the better failure.
cat > "$RPM_TOP/SPECS/vcut-gui.spec" <<EOF
Name:           vcut-gui
Version:        $VERSION
Release:        1
Summary:        $SUMMARY
License:        GPL-3.0-or-later
URL:            https://github.com/Wikimedians-of-Kerala/vcut-gui
BuildArch:      x86_64
Requires:       mpv-libs

# The bundle carries its own Python and Qt. Left on, rpmbuild would read
# every bundled library and demand the system provide them all.
AutoReqProv:    no

%description
$DESCRIPTION

%install
cp -a "$STAGE"/. %{buildroot}/

%files
$PREFIX
/usr/bin/vcut-gui
/usr/share/applications/vcut-gui.desktop
/usr/share/icons/hicolor/scalable/apps/vcut-gui.svg
%doc /usr/share/doc/vcut-gui

%post
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi

%postun
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi
EOF

rpmbuild --define "_topdir $RPM_TOP" \
         --define "_build_id_links none" \
         -bb "$RPM_TOP/SPECS/vcut-gui.spec" >/dev/null

RPM="dist/vcut-gui-${VERSION}-1.x86_64.rpm"
rm -f "$RPM"
mv "$RPM_TOP"/RPMS/x86_64/*.rpm "$RPM"
rm -rf "$RPM_TOP"

# ---------------------------------------------------------------------------
# Check what was produced actually contains the program
# ---------------------------------------------------------------------------
echo "==> Checking the packages"
# Listings go to a file first: piping straight into grep -q closes the pipe
# on the first match, and dpkg-deb dies of SIGPIPE mid-listing, which looks
# exactly like a package that is missing the file.
listing=$(mktemp)
trap 'rm -rf "$STAGE"; rm -f "$listing"' EXIT

dpkg-deb -c "$DEB" > "$listing"
if ! grep -q " \.$PREFIX/vcut-gui\$" "$listing"; then
    echo "error: the .deb does not contain $PREFIX/vcut-gui" >&2
    exit 1
fi

# --dbpath to an empty directory: querying a *file* needs no database, but
# rpm opens the system one anyway and fails where there is none, as on
# Debian. Errors are not discarded -- a silent failure here would leave the
# listing empty and the check would pass on nothing at all.
rpmdb_stub=$(mktemp -d)
if ! rpm -qlp --dbpath "$rpmdb_stub" "$RPM" > "$listing"; then
    rm -rf "$rpmdb_stub"
    echo "error: could not read back $RPM" >&2
    exit 1
fi
rm -rf "$rpmdb_stub"
if ! grep -qx "$PREFIX/vcut-gui" "$listing"; then
    echo "error: the .rpm does not contain $PREFIX/vcut-gui" >&2
    exit 1
fi

echo
echo "Built:"
du -h "$DEB" "$RPM"
