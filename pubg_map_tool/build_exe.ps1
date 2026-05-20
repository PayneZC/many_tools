#Requires -Version 5.1
$ErrorActionPreference = "Stop"
chcp 65001 | Out-Null
& (Join-Path $PSScriptRoot "build_exe.bat")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
