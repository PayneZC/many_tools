#Requires -Version 5.1
# 压枪宏打包脚本（共用 shared 下 Conda/Tcl/Tk 配置）
$ErrorActionPreference = "Stop"

[Console]::InputEncoding = [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
$OutputEncoding = [Console]::OutputEncoding

$ToolDir = (Resolve-Path $PSScriptRoot).Path
$Root = Split-Path -Parent $ToolDir
$SharedDir = Join-Path $Root "shared"
. (Join-Path $SharedDir "build_conda_common.ps1")
Set-Location $Root

$BuildName = "recoil_macro"

$Py = Get-BuildPythonExe
if (-not $Py) {
    throw "No usable Python found. Install Python 3 or Miniconda/Anaconda."
}

Write-Host "Using Python: $Py"
Write-Host ""

Write-Host "[1/4] Installing dependencies from project root..."
& $Py -m pip install -r (Join-Path $Root "requirements.txt") -q
if ($LASTEXITCODE -ne 0) { throw "pip install failed." }

Write-Host "[2/4] Checking PyInstaller..."
& $Py -m pip install "pyinstaller>=6.0.0" -q
if ($LASTEXITCODE -ne 0) { throw "PyInstaller install failed." }

Write-Host "[3/4] Building single-file exe..."
$tkArgs = Get-TkinterPyInstallerArgs $Py
$entry = Join-Path $ToolDir "main.py"
$distDir = Join-Path $Root "dist"
$workDir = Join-Path $ToolDir "build"

& $Py -m PyInstaller --noconfirm --onefile --noconsole `
    --specpath $ToolDir `
    --distpath $distDir `
    --workpath $workDir `
    --paths $ToolDir `
    --paths $SharedDir `
    --hidden-import tool_branding `
    --name $BuildName `
    --hidden-import follow_core `
    --hidden-import config `
    --hidden-import pynput.keyboard._win32 `
    --hidden-import pynput.mouse._win32 `
    --collect-all cv2 `
    @tkArgs `
    $entry
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

Write-Host "[4/4] Renaming exe to Chinese display name..."
& $Py (Join-Path $ToolDir "finalize_build.py")
if ($LASTEXITCODE -ne 0) { throw "finalize_build failed." }

Write-Host ""
Write-Host "Build finished."
