#Requires -Version 5.1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$ToolDir = Join-Path $Root "network_auth_manager"
. (Join-Path $Root "shared\build_conda_common.ps1")
Set-Location $Root
$SharedDir = Join-Path $Root "shared"

$Py = Get-BuildPythonExe
if (-not $Py) { throw "No usable Python found." }
Write-Host "Using Python: $Py"

& $Py -m pip install -r (Join-Path $Root "requirements.txt") -q
& $Py -m pip install "pyinstaller>=6.0.0" -q
if ($LASTEXITCODE -ne 0) { throw "pip install failed." }

$tkArgs = Get-TkinterPyInstallerArgs $Py
$distDir = Join-Path $Root "dist"
$workDir = Join-Path $ToolDir "build"
$iconIco = Join-Path $ToolDir "app_icon.ico"
$iconPng = Join-Path $ToolDir "app_icon.png"

& $Py -m PyInstaller --noconfirm --onefile --noconsole `
    --specpath $ToolDir `
    --distpath $distDir `
    --workpath $workDir `
    --paths $SharedDir `
    --hidden-import tool_branding `
    --hidden-import pystray `
    --hidden-import PIL `
    --hidden-import PIL._tkinter_finder `
    --collect-all pystray `
    --name NetworkAuthManager `
    --icon $iconIco `
    --add-data "${iconIco};." `
    --add-data "${iconPng};." `
    @tkArgs `
    (Join-Path $ToolDir "main.py")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

Rename-DistExe $Py $Root "NetworkAuthManager"
Write-Host "Build finished."
