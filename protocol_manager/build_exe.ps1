#Requires -Version 5.1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "[1/2] 检查 PyInstaller..."
python -m pip install "pyinstaller>=6.0.0" -q

Write-Host "[2/2] 打包单文件 exe..."
python -m PyInstaller --noconfirm protocol_manager/protocol_manager.spec

Write-Host ""
Write-Host "完成: dist\本地协议配置管理器.exe"
