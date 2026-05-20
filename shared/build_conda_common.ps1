#Requires -Version 5.1
# 各 tkinter 小工具 PyInstaller 打包共用：Miniconda Python + Conda DLL/Tcl/Tk 资源

$script:SharedDir = $PSScriptRoot

$script:CondaDllNames = @(
    "ffi.dll", "ffi-8.dll", "ffi-7.dll",
    "libexpat.dll", "tcl86t.dll", "tk86t.dll",
    "LIBBZ2.dll", "libbz2.dll", "liblzma.dll", "libmpdec-4.dll",
    "libssl-3-x64.dll", "libcrypto-3-x64.dll", "zlib.dll"
)

function Get-BuildPythonExe {
    $candidates = @(
        (Join-Path $env:USERPROFILE "miniconda3\python.exe")
        (Join-Path $env:USERPROFILE "anaconda3\python.exe")
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe")
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe")
    )
    foreach ($path in $candidates) {
        if (Test-Path $path) { return $path }
    }
    $cmdPy = Get-Command python -ErrorAction SilentlyContinue
    if ($cmdPy) { return $cmdPy.Source }
    return $null
}

function Get-SharedDir {
    return $script:SharedDir
}

function Get-CondaBinaryArgs([string]$Py) {
    $prefix = & $Py -c "import sys; print(sys.prefix)"
    $binDir = Join-Path $prefix "Library\bin"
    $dllDir = Join-Path $prefix "DLLs"
    $args = @()
    $seen = @{}
    foreach ($name in $script:CondaDllNames) {
        foreach ($folder in @($binDir, $dllDir)) {
            $dll = Join-Path $folder $name
            if ((Test-Path $dll) -and -not $seen.ContainsKey($name.ToLower())) {
                $args += @("--add-binary", "${dll};.")
                $seen[$name.ToLower()] = $true
                break
            }
        }
    }
    return $args
}

function Get-CondaTclTkDataArgs([string]$Py) {
    $prefix = & $Py -c "import sys; print(sys.prefix)"
    $lib = Join-Path $prefix "Library\lib"
    $args = @()
    $tcl = Join-Path $lib "tcl8.6"
    $tk = Join-Path $lib "tk8.6"
    if (Test-Path $tcl) { $args += @("--add-data", "${tcl};tcl8.6") }
    if (Test-Path $tk) { $args += @("--add-data", "${tk};tk8.6") }
    return $args
}

function Get-TkinterPyInstallerArgs([string]$Py) {
    $hook = Join-Path $script:SharedDir "rthook_tkinter_runtime.py"
    $args = @(
        "--collect-all", "tkinter",
        "--runtime-hook", $hook
    )
    $args += Get-CondaBinaryArgs $Py
    $args += Get-CondaTclTkDataArgs $Py
    return $args
}

function Rename-DistExe([string]$Py, [string]$Root, [string]$AsciiName) {
    $script = Join-Path $script:SharedDir "finalize_dist_rename.py"
    & $Py $script $AsciiName
    if ($LASTEXITCODE -ne 0) { throw "Rename failed: $AsciiName" }
}
