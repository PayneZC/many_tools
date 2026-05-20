# -*- coding: utf-8 -*-
"""
打包后处理：将 ASCII 产物重命名为「PUBG地图工具.exe」，并做启动冒烟测试。
避免 PyInstaller 在部分控制台下用中文名写出乱码 exe、旧文件残留。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent
ROOT = TOOL_DIR.parent
DIST = ROOT / "dist"
# 与 pubg_map_tool.spec 中 EXE name 一致（仅用 ASCII）
BUILD_NAME = "PUBGMapTool_build"
BUILD_EXE = DIST / f"{BUILD_NAME}.exe"
DISPLAY_EXE_NAME = "PUBG地图工具.exe"
FINAL_EXE = DIST / DISPLAY_EXE_NAME
PUBG_GLOB = "PUBG*.exe"


def _remove_pubg_exes() -> None:
    """删除 dist 下所有 PUBG 相关 exe（含旧中文名、乱码名）。"""
    if not DIST.is_dir():
        return
    for path in DIST.glob(PUBG_GLOB):
        try:
            path.unlink()
        except OSError as exc:
            print(f"无法删除 {path.name}: {exc}", file=sys.stderr)
            sys.exit(1)


def _rename_build_output() -> None:
    """将 PyInstaller 输出的 ASCII 名 exe 重命名为最终中文名。"""
    if not BUILD_EXE.is_file():
        print(f"未找到构建产物: {BUILD_EXE}", file=sys.stderr)
        sys.exit(1)
    if FINAL_EXE.is_file():
        FINAL_EXE.unlink()
    shutil.move(str(BUILD_EXE), str(FINAL_EXE))
    print(f"已输出: {FINAL_EXE}")


def _smoke_test() -> None:
    """子进程快速验证 tkinter、ctypes、主窗口可初始化后退出。"""
    proc = subprocess.run(
        [str(FINAL_EXE), "--startup-check"],
        cwd=str(DIST),
        capture_output=True,
        text=True,
        timeout=60,
        errors="replace",
    )
    if proc.returncode != 0:
        print("启动冒烟测试失败:", file=sys.stderr)
        if proc.stdout:
            print(proc.stdout, file=sys.stderr)
        if proc.stderr:
            print(proc.stderr, file=sys.stderr)
        sys.exit(1)
    print("启动冒烟测试通过")


def main() -> None:
    action = (sys.argv[1] if len(sys.argv) > 1 else "finalize").lower()
    if action == "clean":
        _remove_pubg_exes()
        return
    if action == "finalize":
        _rename_build_output()
        _smoke_test()
        return
    print(f"未知参数: {action}，支持 clean | finalize", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
