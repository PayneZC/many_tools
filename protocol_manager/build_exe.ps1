#Requires -Version 5.1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$ToolDir = Join-Path $Root "protocol_manager"
Set-Location $Root

Write-Host "[1/2] 检查 PyInstaller..."
python -m pip install "pyinstaller>=6.0.0" -q
if ($LASTEXITCODE -ne 0) { throw "pip install failed. Please verify Python is in PATH." }

Write-Host "[2/2] 打包单文件 exe..."
python -m PyInstaller --noconfirm --onefile --noconsole --specpath "$ToolDir" --name "本地协议配置管理器" "$ToolDir/main.py"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

Write-Host ""
Write-Host "完成: dist\本地协议配置管理器.exe"
Write-Host "spec: protocol_manager\本地协议配置管理器.spec"
