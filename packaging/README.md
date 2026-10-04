# Packaging

The full build documentation is in [docs/BUILDING.md](../docs/BUILDING.md):
how to build for each platform, what is inside the bundle, what is left out
and why, and what to do when a build fails.

End-user installation instructions are in [INSTALL.md](../INSTALL.md).

This directory holds the pieces:

| File | What it is |
| --- | --- |
| `build-linux.sh` | Builds `dist/vcut-gui-linux.tar.gz` |
| `build-windows.ps1` | Builds `dist\vcut-gui-windows.zip` (run on Windows) |
| `entry.py` | The bundle's entry point — **not** `src/vcut/gui/app.py` |
| `install.sh` | Installs an unpacked Linux build system-wide |
| `vcut-gui.desktop` | The Linux menu entry |

The PyInstaller spec is `vcut-gui.spec` in the repository root.
