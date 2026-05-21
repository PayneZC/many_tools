#Requires -Version 5.1
# 520 浪漫空间 — 单文件 exe（内嵌 HTML/CSS/JS，Edge/Chrome 应用模式启动）
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$ToolDir = $PSScriptRoot
. (Join-Path $Root "shared\build_conda_common.ps1")
Set-Location $Root

$Py = Get-BuildPythonExe
if (-not $Py) { throw "No usable Python found." }
Write-Host "Using Python: $Py"

& $Py -m pip install "pyinstaller>=6.0.0" -q
if ($LASTEXITCODE -ne 0) { throw "pip install failed." }

$distDir = Join-Path $Root "dist"
$workDir = Join-Path $ToolDir "build"
$indexHtml = Join-Path $ToolDir "index.html"
$cssDir = Join-Path $ToolDir "css"
$jsDir = Join-Path $ToolDir "js"

if (-not (Test-Path $indexHtml)) { throw "Missing index.html" }

$configJs = Join-Path $ToolDir "js\config.js"
$dataArgs = @(
    "--add-data", "${indexHtml};.",
    "--add-data", "${cssDir};css",
    "--add-data", "${jsDir};js"
)
if (-not (Test-Path $configJs)) { throw "Missing js\config.js" }

$condaArgs = Get-CondaBinaryArgs $Py

& $Py -m PyInstaller --noconfirm --onefile --noconsole `
    --specpath $ToolDir `
    --distpath $distDir `
    --workpath $workDir `
    --name Love520Box `
    @condaArgs `
    @dataArgs `
    (Join-Path $ToolDir "launcher.py")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

Rename-DistExe $Py $Root "Love520Box"
Write-Host "Done. Output: dist\520浪漫盒.exe"
