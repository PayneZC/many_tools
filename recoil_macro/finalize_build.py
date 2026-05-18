"""
打包完成后将 exe 重命名为中文显示名（避免 PyInstaller/PowerShell 传参乱码）。
"""

from __future__ import annotations

from pathlib import Path

# PyInstaller 内部使用的 ASCII 名称（避免 spec/build 路径乱码）
BUILD_NAME = "recoil_macro"
# 发布给用户的中文 exe 文件名
DISPLAY_EXE_NAME = "鼠标辅助工具.exe"


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    src = root / "dist" / f"{BUILD_NAME}.exe"
    dst = root / "dist" / DISPLAY_EXE_NAME

    if not src.is_file():
        print(f"[错误] 未找到打包产物: {src}")
        return 1

    if dst.exists():
        dst.unlink()
    src.replace(dst)
    print(f"[完成] {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
