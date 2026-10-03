# Packaging

## Both platforms

```sh
uv pip install pyinstaller
pyinstaller vcut-gui.spec
```

The result is `dist/vcut-gui/`, which can be zipped and copied to another
machine of the same operating system.

## FFmpeg

FFmpeg is not bundled — it is large, and which codecs a build carries (and
under which licence) varies. The app finds `ffmpeg` and `ffprobe` on `PATH`,
and the setup screen says so plainly when they are missing or when the build
has no AV1 encoder.

To ship FFmpeg with the application, copy `ffmpeg` and `ffprobe` (with `.exe`
on Windows) into `dist/vcut-gui/` next to the executable.

For Commons-ready output the build needs `libsvtav1` (or `libvpx-vp9`) and
`libopus`. Check with:

```sh
ffmpeg -encoders | grep -E "libsvtav1|libvpx-vp9|libopus"
```

## Linux desktop entry

```sh
sudo cp dist/vcut-gui/vcut-gui /usr/local/bin/
sudo cp packaging/vcut-gui.desktop /usr/share/applications/
```

## Windows notes

- Build on Windows; PyInstaller does not cross-compile.
- Unsigned executables draw a SmartScreen warning on first run.
