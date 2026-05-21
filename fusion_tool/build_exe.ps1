#Requires -Version 5.1
# PUBG 辅助工具打包（地图 + 压枪）
$ErrorActionPreference = "Stop"

[Console]::InputEncoding = [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
$OutputEncoding = [Console]::OutputEncoding

$ToolDir = (Resolve-Path $PSScriptRoot).Path
$Root = Split-Path -Parent $ToolDir
$PubgDir = Join-Path $Root "pubg_map_tool"
$SharedDir = Join-Path $Root "shared"
. (Join-Path $SharedDir "build_conda_common.ps1")
Set-Location $Root

$BuildName = "FusionTool_build"

$Py = Get-BuildPythonExe
if (-not $Py) {
    throw "No usable Python found. Install Python 3 or Miniconda/Anaconda."
}

Write-Host "Using Python: $Py"
Write-Host ""

Write-Host "[1/5] Installing dependencies..."
& $Py -m pip install -r (Join-Path $Root "requirements.txt") -q
if ($LASTEXITCODE -ne 0) { throw "pip install failed." }

Write-Host "[2/5] Checking PyInstaller..."
& $Py -m pip install "pyinstaller>=6.0.0" "pillow-avif-plugin>=1.4.0" -q
if ($LASTEXITCODE -ne 0) { throw "PyInstaller install failed." }

Write-Host "[3/5] Cleaning old build output..."
Get-Process -Name "FusionTool_build","PUBG辅助工具","融合工具" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 800
& $Py (Join-Path $ToolDir "finalize_build.py") clean
if ($LASTEXITCODE -ne 0) { throw "clean failed." }

Write-Host "[4/5] Building single-file exe..."
$tkArgs = Get-TkinterPyInstallerArgs $Py
$entry = Join-Path $ToolDir "main.py"
$distDir = Join-Path $Root "dist"
$workDir = Join-Path $ToolDir "build"
$iconIco = Join-Path $ToolDir "app_icon.ico"
$iconArgs = @()
if (Test-Path $iconIco) {
    $iconArgs += @("--icon", $iconIco)
}
$dataArgs = @()
$iconPng = Join-Path $ToolDir "app_icon.png"
if (Test-Path $iconPng) {
    $dataArgs += @("--add-data", "${iconPng};.")
}
if (Test-Path $iconIco) {
    $dataArgs += @("--add-data", "${iconIco};.")
}
$weiPng = Join-Path $SharedDir "wei.png"
$zhiJpg = Join-Path $SharedDir "zhi.jpg"
if (Test-Path $weiPng) {
    $dataArgs += @("--add-data", "${weiPng};.")
}
if (Test-Path $zhiJpg) {
    $dataArgs += @("--add-data", "${zhiJpg};.")
}

& $Py -m PyInstaller --noconfirm --onefile --noconsole `
    --specpath $ToolDir `
    --distpath $distDir `
    --workpath $workDir `
    --paths $ToolDir `
    --paths $PubgDir `
    --paths $SharedDir `
    --hidden-import tool_branding `
    --hidden-import persist_paths `
    --hidden-import recoil_config `
    --hidden-import app_settings `
    --hidden-import donation_window `
    --hidden-import single_instance `
    --hidden-import app_icon `
    --hidden-import map_catalog `
    --hidden-import map_fetcher `
    --hidden-import overlay_window `
    --hidden-import overlay_settings `
    --hidden-import overlay_hotkey `
    --hidden-import preview_cache `
    --hidden-import pillow_avif `
    --hidden-import pynput.mouse._win32 `
    --hidden-import pynput.keyboard._win32 `
    --hidden-import pystray `
    --collect-all pystray `
    @iconArgs `
    @dataArgs `
    @tkArgs `
    --name $BuildName `
    $entry
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

Write-Host "[5/5] Renaming exe to Chinese display name..."
& $Py (Join-Path $ToolDir "finalize_build.py") finalize
if ($LASTEXITCODE -ne 0) { throw "finalize_build failed." }

Write-Host ""
Write-Host "Build finished: dist\PUBG辅助工具.exe"
