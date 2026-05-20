#Requires -Version 5.1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$ToolDir = Join-Path $Root "search_tool_app"
. (Join-Path $Root "shared\build_conda_common.ps1")
Set-Location $Root
$SharedDir = Join-Path $Root "shared"

$Py = Get-BuildPythonExe
if (-not $Py) { throw "No usable Python found." }
Write-Host "Using Python: $Py"

& $Py -m pip install "pyinstaller>=6.0.0" -q
if ($LASTEXITCODE -ne 0) { throw "pip install failed." }

$tkArgs = Get-TkinterPyInstallerArgs $Py
$distDir = Join-Path $Root "dist"
$workDir = Join-Path $ToolDir "build"

& $Py -m PyInstaller --noconfirm --onefile --noconsole `
    --specpath $ToolDir `
    --distpath $distDir `
    --workpath $workDir `
    --paths $SharedDir `
    --hidden-import tool_branding `
    --name DirectorySearchTool `
    @tkArgs `
    (Join-Path $ToolDir "main.py")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

Rename-DistExe $Py $Root "DirectorySearchTool"
Write-Host "Build finished."
