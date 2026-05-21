# -*- coding: utf-8 -*-
"""将 dist 下 ASCII 构建名 exe 重命名为中文显示名。"""
from __future__ import annotations

import sys
from pathlib import Path

# ASCII 构建名 -> 中文 exe 显示名（避免 PowerShell 传参乱码）
DISPLAY_NAMES: dict[str, str] = {
    "DirectorySearchTool": "目录字符串查询工具",
    "ProtocolManager": "本地协议配置管理器",
    "PortManager": "端口管理工具",
    "NetworkAuthManager": "网络认证自动保活工具",
    "Love520Box": "520浪漫盒",
}


def _kill_holders(exe: Path) -> None:
    """结束正在运行同一 exe 的进程（仅 Windows）。"""
    if sys.platform != "win32":
        return
    import subprocess

    try:
        subprocess.run(
            ["taskkill", "/F", "/IM", exe.name],
            capture_output=True,
            timeout=10,
            check=False,
        )
    except Exception:
        pass


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: finalize_dist_rename.py <ascii_name>")
        return 1
    ascii_name = sys.argv[1]
    display = DISPLAY_NAMES.get(ascii_name)
    if not display:
        print(f"Unknown build name: {ascii_name}")
        return 1

    # shared/ 的上级目录即仓库根目录
    root = Path(__file__).resolve().parent.parent
    dist = root / "dist"
    src = dist / f"{ascii_name}.exe"
    dst = dist / f"{display}.exe"
    if not src.is_file():
        print(f"Missing: {src}")
        return 1
    if dst.exists():
        _kill_holders(dst)
        try:
            dst.unlink()
        except OSError as exc:
            print(f"Cannot remove old exe (close running app first): {dst}")
            print(exc)
            return 1
    src.rename(dst)
    print("OK:", ascii_name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
