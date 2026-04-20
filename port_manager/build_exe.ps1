#Requires -Version 5.1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$ToolDir = Join-Path $Root "port_manager"
Set-Location $Root

Write-Host "[1/2] 检查 PyInstaller..."
python -m pip install "pyinstaller>=6.0.0" -q
if ($LASTEXITCODE -ne 0) { throw "pip install failed. Please verify Python is in PATH." }

Write-Host "[2/2] 打包单文件 exe..."
python -m PyInstaller --noconfirm --onefile --noconsole --specpath "$ToolDir" --name "端口管理工具" --icon "$ToolDir/port_icon.ico" --add-data "$ToolDir/port_icon.ico;." "$ToolDir/port_manager.py"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

Write-Host ""
Write-Host "完成: dist\端口管理工具.exe"
Write-Host "spec: port_manager\端口管理工具.spec"
