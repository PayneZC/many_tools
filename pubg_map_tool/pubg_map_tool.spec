# -*- mode: python ; coding: utf-8 -*-
"""
PUBG 地图工具 PyInstaller 规格文件。
构建：python -m PyInstaller --noconfirm --clean pubg_map_tool/pubg_map_tool.spec
"""
import sys
from pathlib import Path

TOOL_DIR = Path(SPECPATH)
ROOT = TOOL_DIR.parent
SHARED_DIR = ROOT / "shared"
# 统一输出到仓库根目录 dist/（与 build_exe.bat 的 cd 无关）
distpath = str(ROOT / "dist")
workpath = str(ROOT / "build" / "pubg_map_tool")
PREFIX = Path(sys.prefix)
BIN_DIR = PREFIX / "Library" / "bin"
DLL_DIR = PREFIX / "DLLs"


def _collect_binaries() -> list[tuple[str, str]]:
    # Conda 运行库：tkinter、ctypes(_ctypes)、ssl(urllib) 所需
    names = (
        "tcl86t.dll",
        "tk86t.dll",
        "ffi.dll",
        "ffi-8.dll",
        "ffi-7.dll",
        "libcrypto-3-x64.dll",
        "libssl-3-x64.dll",
        "liblzma.dll",
        "libbz2.dll",
        "libexpat.dll",
        "libmpdec-4.dll",
        "libzstd.dll",
        "zlib.dll",
    )
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for name in names:
        for folder in (BIN_DIR, DLL_DIR):
            path = folder / name
            if path.is_file() and name.lower() not in seen:
                out.append((str(path), "."))
                seen.add(name.lower())
                break
    # _zstd.pyd 依赖 zstd.dll（Conda 中文件名为 libzstd.dll）
    libzstd = BIN_DIR / "libzstd.dll"
    zstd_alias = TOOL_DIR / "build_deps" / "zstd.dll"
    if libzstd.is_file():
        out.append((str(libzstd), "."))
        seen.add("libzstd.dll")
        try:
            zstd_alias.parent.mkdir(parents=True, exist_ok=True)
            if not zstd_alias.is_file() or zstd_alias.stat().st_mtime < libzstd.stat().st_mtime:
                import shutil

                shutil.copy2(libzstd, zstd_alias)
            out.append((str(zstd_alias), "."))
            seen.add("zstd.dll")
        except OSError:
            pass
    return out


def _collect_datas() -> list[tuple[str, str]]:
    lib = PREFIX / "Library" / "lib"
    datas: list[tuple[str, str]] = []
    tcl = lib / "tcl8.6"
    tk = lib / "tk8.6"
    if tcl.is_dir():
        datas.append((str(tcl), "tcl8.6"))
    if tk.is_dir():
        datas.append((str(tk), "tk8.6"))
    for name in ("app_icon.png", "app_icon.ico"):
        path = TOOL_DIR / name
        if path.is_file():
            datas.append((str(path), "."))
    return datas


hiddenimports = [
    "tool_branding",
    "app_icon",
    "map_catalog",
    "map_fetcher",
    "overlay_window",
    "overlay_settings",
    "overlay_hotkey",
    "preview_cache",
    "pillow_avif",
    "pynput.keyboard._win32",
]

_icon = TOOL_DIR / "app_icon.ico"

a = Analysis(
    [str(TOOL_DIR / "main.py")],
    pathex=[str(TOOL_DIR), str(SHARED_DIR)],
    binaries=_collect_binaries(),
    datas=_collect_datas(),
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(SHARED_DIR / "rthook_tkinter_runtime.py")],
    excludes=["numpy", "matplotlib", "pandas"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    # 使用 ASCII 中间名，由 post_build.py 重命名为 PUBG地图工具.exe
    name="PUBGMapTool_build",
    icon=str(_icon) if _icon.is_file() else None,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
