# -*- coding: utf-8 -*-
"""
注释：打包后将 ASCII 产物重命名为中文显示名，避免控制台编码导致 exe 名乱码。
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent
ROOT = TOOL_DIR.parent
DIST = ROOT / "dist"
BUILD_NAME = "FusionTool_build"
BUILD_EXE = DIST / f"{BUILD_NAME}.exe"
DISPLAY_EXE_NAME = "PUBG辅助工具.exe"
FINAL_EXE = DIST / DISPLAY_EXE_NAME
# 注释：清理历史构建产物（含旧中文名）。
_CLEAN_GLOBS = ("Fusion*.exe", "融合工具.exe", DISPLAY_EXE_NAME)


def _remove_old_exes() -> None:
    if not DIST.is_dir():
        return
    seen: set[Path] = set()
    for pattern in _CLEAN_GLOBS:
        for path in DIST.glob(pattern):
            if path in seen:
                continue
            seen.add(path)
            try:
                path.unlink()
            except OSError as exc:
                print(f"无法删除 {path.name}: {exc}", file=sys.stderr)
                sys.exit(1)


def _rename_build_output() -> None:
    if not BUILD_EXE.is_file():
        print(f"未找到构建产物: {BUILD_EXE}", file=sys.stderr)
        sys.exit(1)
    if FINAL_EXE.is_file():
        FINAL_EXE.unlink()
    shutil.move(str(BUILD_EXE), str(FINAL_EXE))
    print(f"已输出: {FINAL_EXE}")


def main() -> None:
    action = (sys.argv[1] if len(sys.argv) > 1 else "finalize").lower()
    if action == "clean":
        _remove_old_exes()
        return
    if action == "finalize":
        _rename_build_output()
        return
    print(f"未知参数: {action}，支持 clean | finalize", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
