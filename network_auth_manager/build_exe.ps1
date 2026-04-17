#Requires -Version 5.1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$ToolDir = Join-Path $Root "network_auth_manager"
Set-Location $Root

Write-Host "[1/2] Check PyInstaller..."
python -m pip install "pyinstaller>=6.0.0" -q
if ($LASTEXITCODE -ne 0) { throw "pip install failed. Please verify Python is in PATH." }

Write-Host "[2/2] Build onefile exe..."
python -m PyInstaller --noconfirm --onefile --noconsole --specpath "$ToolDir" --name "网络认证自动保活工具" --icon "$ToolDir/app_icon.ico" --add-data "$ToolDir/app_icon.ico;." --add-data "$ToolDir/app_icon.png;." "$ToolDir/main.py"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

Write-Host ""
Write-Host "Done: dist output generated"
Write-Host "Spec path: network_auth_manager\*.spec"
