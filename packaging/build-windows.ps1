# Build the Windows package: dist\vcut-gui-windows.zip
#
#     powershell -ExecutionPolicy Bypass -File packaging\build-windows.ps1
#
# Run this on Windows: PyInstaller does not cross-compile.
# FFmpeg is not bundled; see INSTALL.md.
$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

Write-Host "==> Preparing the build environment"
# Pin the interpreter rather than taking whatever uv finds: a CI image may
# ship several, and the bundle embeds whichever one builds it.
$python = if ($env:VCUT_PYTHON) { $env:VCUT_PYTHON } else { "3.12" }
uv venv --quiet --clear --python $python .venv-build
uv pip install --quiet --python .venv-build\Scripts\python.exe -e . pyinstaller

Write-Host "==> Building"
if (Test-Path build) { Remove-Item -Recurse -Force build }
if (Test-Path dist\vcut-gui) { Remove-Item -Recurse -Force dist\vcut-gui }
if (Test-Path dist\vcut-gui-windows.zip) { Remove-Item dist\vcut-gui-windows.zip }
.venv-build\Scripts\pyinstaller.exe --noconfirm --clean vcut-gui.spec

if (-not (Test-Path dist\vcut-gui\vcut-gui.exe)) {
    throw "PyInstaller did not produce dist\vcut-gui\vcut-gui.exe"
}

Write-Host "==> Fetching libmpv"
# Qt's bundled FFmpeg has no AV1 decoder, so without libmpv an AV1 recording
# shows as a black rectangle on the screen whose whole job is finding cut
# points by eye. There is no Windows package to depend on, so the DLL is
# shipped in the bundle; python-mpv finds it on PATH, which the program adds
# at startup. Linux installs libmpv2 from the distribution instead.
$mpvDll = "dist\vcut-gui\libmpv-2.dll"
if (-not (Test-Path $mpvDll)) {
    $headers = @{ "User-Agent" = "vcut-gui-build" }
    if ($env:GITHUB_TOKEN) { $headers["Authorization"] = "Bearer $env:GITHUB_TOKEN" }
    $release = Invoke-RestMethod -Headers $headers `
        -Uri "https://api.github.com/repos/shinchiro/mpv-winbuild-cmake/releases/latest"
    # The "dev" archive is the one with the DLL and its import library; the
    # plain one is the player. "v3" is built for newer CPUs only.
    $asset = $release.assets |
        Where-Object { $_.name -like "mpv-dev-x86_64-2*" -and $_.name -notlike "*v3*" } |
        Select-Object -First 1
    if (-not $asset) { throw "no mpv-dev-x86_64 archive in the latest release" }

    Write-Host "    $($asset.name)"
    $archive = Join-Path $env:TEMP $asset.name
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $archive
    $extracted = Join-Path $env:TEMP "mpv-dev"
    if (Test-Path $extracted) { Remove-Item -Recurse -Force $extracted }
    # 7-Zip is present on the GitHub Windows runners.
    & 7z x -y "-o$extracted" $archive | Out-Null
    $dll = Get-ChildItem -Path $extracted -Filter "libmpv-2.dll" -Recurse |
        Select-Object -First 1
    if (-not $dll) { throw "libmpv-2.dll not found in $($asset.name)" }
    Copy-Item $dll.FullName $mpvDll
}
if (-not (Test-Path $mpvDll)) { throw "libmpv-2.dll was not bundled" }

Write-Host "==> Checking the bundle starts"
# Catches entry-point and missing-import faults, which only appear once the
# app runs outside a Python environment.
#
# Start-Process -Wait, not the call operator: console=False in the spec makes
# this a GUI-subsystem binary, which PowerShell does not wait for, so
# $LASTEXITCODE would be read before the app had finished -- or not set at
# all. Start-Process waits and hands back the real exit code.
Push-Location dist\vcut-gui
$env:QT_QPA_PLATFORM = "offscreen"
try {
    $run = Start-Process -FilePath ".\vcut-gui.exe" -ArgumentList "--self-test" `
        -Wait -PassThru -NoNewWindow
    $started = $run.ExitCode
} finally {
    Remove-Item Env:\QT_QPA_PLATFORM -ErrorAction SilentlyContinue
    Pop-Location
}
if ($started -ne 0) {
    throw "the built application failed to start (exit code $started)"
}

Write-Host "==> Adding the documentation"
Copy-Item INSTALL.md dist\vcut-gui\
Copy-Item README.md dist\vcut-gui\
Copy-Item src\vcut\gui\logo\vcutcli-logo.svg dist\vcut-gui\vcut-gui.svg

Write-Host "==> Packing"
if (Test-Path dist\vcut-gui-windows.zip) { Remove-Item dist\vcut-gui-windows.zip }
Compress-Archive -Path dist\vcut-gui -DestinationPath dist\vcut-gui-windows.zip

Write-Host ""
Write-Host "Built dist\vcut-gui-windows.zip"
Get-Item dist\vcut-gui-windows.zip | Select-Object Name, @{n="MB";e={[math]::Round($_.Length/1MB,1)}}
