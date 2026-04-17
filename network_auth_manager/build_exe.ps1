#Requires -Version 5.1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "[1/2] 检查 PyInstaller..."
python -m pip install "pyinstaller>=6.0.0" -q

Write-Host "[2/2] 打包单文件 exe..."
python -m PyInstaller --noconfirm --onefile --noconsole --name "网络认证自动保活工具" --icon "network_auth_manager/app_icon.ico" --add-data "network_auth_manager/app_icon.ico;." --add-data "network_auth_manager/app_icon.png;." network_auth_manager/main.py

Write-Host ""
Write-Host "完成: dist\网络认证自动保活工具.exe"
