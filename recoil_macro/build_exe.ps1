#Requires -Version 5.1
# 压枪宏打包脚本（含 Conda 环境 DLL 补齐）
$ErrorActionPreference = "Stop"

# 强制 UTF-8，降低控制台与脚本编码不一致问题
[Console]::InputEncoding = [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
$OutputEncoding = [Console]::OutputEncoding

$ToolDir = (Resolve-Path $PSScriptRoot).Path
$Root = Split-Path -Parent $ToolDir
Set-Location $Root

# PyInstaller 使用 ASCII 名称，中文显示名由 finalize_build.py 重命名
$BuildName = "recoil_macro"

$CondaDllNames = @(
    "ffi.dll", "libexpat.dll", "tcl86t.dll", "tk86t.dll",
    "LIBBZ2.dll", "liblzma.dll", "libmpdec-4.dll",
    "libssl-3-x64.dll", "libcrypto-3-x64.dll"
)

function Get-PythonExe {
    $candidates = @(
        (Join-Path $env:USERPROFILE "miniconda3\python.exe")
        (Join-Path $env:USERPROFILE "anaconda3\python.exe")
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe")
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe")
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe")
    )
    foreach ($path in $candidates) {
        if (Test-Path $path) { return $path }
    }
    $cmdPy = Get-Command python -ErrorAction SilentlyContinue
    if ($cmdPy) { return $cmdPy.Source }
    return $null
}

function Get-CondaBinaryArgs([string]$Py) {
    $prefix = & $Py -c "import sys; print(sys.prefix)"
    $binDir = Join-Path $prefix "Library\bin"
    if (-not (Test-Path $binDir)) { return @() }
    $args = @()
    foreach ($name in $CondaDllNames) {
        $dll = Join-Path $binDir $name
        if (Test-Path $dll) { $args += @("--add-binary", "${dll};.") }
    }
    return $args
}

$Py = Get-PythonExe
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
$condaArgs = Get-CondaBinaryArgs $Py
$entry = Join-Path $ToolDir "main.py"
$distDir = Join-Path $Root "dist"
$workDir = Join-Path $ToolDir "build"

& $Py -m PyInstaller --noconfirm --onefile --noconsole `
    --specpath $ToolDir `
    --distpath $distDir `
    --workpath $workDir `
    --paths $ToolDir `
    --name $BuildName `
    --hidden-import follow_core `
    --hidden-import config `
    --hidden-import pynput.keyboard._win32 `
    --hidden-import pynput.mouse._win32 `
    --collect-all cv2 `
    --collect-all tkinter `
    @condaArgs `
    $entry
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

Write-Host "[4/4] Renaming exe to Chinese display name..."
& $Py (Join-Path $ToolDir "finalize_build.py")
if ($LASTEXITCODE -ne 0) { throw "finalize_build failed." }

Write-Host ""
Write-Host "Done: dist\鼠标辅助工具.exe"
