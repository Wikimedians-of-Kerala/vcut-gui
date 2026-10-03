# Installing vcut

vcut runs on Windows and Linux. There are three ways to install it, from
easiest to most involved.

| | Who it suits | FFmpeg |
| --- | --- | --- |
| [Ready-made package](#1-ready-made-package) | Most people | Install separately |
| [From PyPI or a wheel](#2-from-a-wheel) | Anyone with Python | Install separately |
| [From source](#3-from-source) | Developers | Install separately |

FFmpeg is never bundled — it is large, and which codecs a build carries
varies with how it was compiled. [Install it first](#installing-ffmpeg).

---

## Installing FFmpeg

vcut needs `ffmpeg` and `ffprobe` on your `PATH`. For Commons-ready output
the build also needs the `libsvtav1` (or `libvpx-vp9`) and `libopus`
encoders — nearly every distributed build has them.

### Windows

The simplest route is winget, in PowerShell:

```powershell
winget install Gyan.FFmpeg
```

Then **close and reopen** PowerShell so the new `PATH` takes effect.

Alternatives: `choco install ffmpeg-full` with Chocolatey, or download a
build from <https://www.gyan.dev/ffmpeg/builds/>, unzip it, and add its
`bin` folder to your `PATH`.

### Linux

```sh
sudo apt install ffmpeg          # Debian, Ubuntu, Mint
sudo dnf install ffmpeg          # Fedora
sudo pacman -S ffmpeg            # Arch
```

Debian and Ubuntu builds include SVT-AV1 from Debian 12 and Ubuntu 23.04
onwards. On anything older, vcut will say so and you can use WebM (VP9).

### Checking it worked

```sh
ffmpeg -version
ffmpeg -encoders | grep -E "libsvtav1|libvpx-vp9|libopus"
```

If the second command prints nothing, your FFmpeg cannot produce
Commons-ready files. vcut will still cut to MP4.

---

## 1. Ready-made package

Download the archive for your system from the
[releases page](https://github.com/ranjithsiji/vcut-gui/releases), unpack it
anywhere, and run it. No Python needed.

### Windows

1. Download `vcut-gui-windows.zip`.
2. Right-click it → **Extract All**.
3. Open the extracted folder and run `vcut-gui.exe`.

Windows SmartScreen will warn that the publisher is unknown, because the
executable is not code-signed. Click **More info** → **Run anyway**.

To put it in the Start menu, right-click `vcut-gui.exe` → **Send to** →
**Desktop**, then move that shortcut into
`%APPDATA%\Microsoft\Windows\Start Menu\Programs`.

### Linux

```sh
tar xf vcut-gui-linux.tar.gz
cd vcut-gui
./vcut-gui
```

To install it for the whole system, with a menu entry:

```sh
sudo ./install.sh
```

That copies the program to `/opt/vcut-gui`, links `vcut-gui` into
`/usr/local/bin`, and adds a desktop entry. `sudo ./install.sh --uninstall`
reverses it.

---

## 2. From a wheel

If you already have Python 3.11 or newer:

```sh
pip install vcut-gui
vcut-gui
```

Or from a downloaded wheel:

```sh
pip install vcut_gui-1.0.1-py3-none-any.whl
```

To upload to Wikimedia Commons from inside the app, add Pywikibot:

```sh
pip install "vcut-gui[upload]"
```

### Keeping it out of your system Python

On Linux, distributions increasingly refuse `pip install` outside a virtual
environment. Either use a virtual environment:

```sh
python3 -m venv ~/.local/share/vcut-venv
~/.local/share/vcut-venv/bin/pip install vcut-gui
~/.local/share/vcut-venv/bin/vcut-gui
```

or let `pipx` handle it:

```sh
pipx install vcut-gui
```

---

## 3. From source

```sh
git clone https://github.com/ranjithsiji/vcut-gui.git
cd vcut-gui
uv venv
uv pip install -e ".[dev]"
uv run vcut-gui
```

Without `uv`:

```sh
python3 -m venv .venv
. .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
vcut-gui
```

Running the tests:

```sh
uv run pytest
```

---

## After installing

Check everything is in place from the app itself: open it, choose a video,
and look at the **Encoding** section on the first screen. It reports which
AV1 encoder FFmpeg offers, or says plainly if there is none.

For uploading, log Pywikibot in once from a terminal:

```sh
pywikibot login
```

Until you do, the upload screen says so and the dry run still works.

---

## If something goes wrong

**"FFmpeg was not found"** — it is not on your `PATH`. Reopen your terminal
after installing it; on Windows a reboot sometimes helps. You can also point
vcut straight at it in the settings.

**The window opens but video does not play** — Qt needs its own multimedia
backend. On Debian and Ubuntu:

```sh
sudo apt install libgstreamer1.0-0 gstreamer1.0-plugins-good gstreamer1.0-libav
```

**"This FFmpeg build has no AV1 encoder"** — your build lacks SVT-AV1.
Choose WebM (VP9) instead; Commons accepts it, and it is actually what
Commons serves to viewers.

**Wayland scaling looks wrong** — try `QT_QPA_PLATFORM=xcb vcut-gui`.

**Nothing happens when you run the Windows executable** — unpack the zip
properly rather than running it from inside the archive viewer.
