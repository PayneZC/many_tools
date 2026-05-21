# -*- coding: utf-8 -*-
"""
520 浪漫空间 — 桌面启动器（单文件 exe）。
将内嵌页面释放到 %TEMP% 后，用 Edge/Chrome 应用模式打开（无地址栏）。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import webbrowser
from pathlib import Path

# 临时目录前缀，便于下次启动时清理旧缓存
_TEMP_PREFIX = "love520_"


def _bundle_dir() -> Path:
    """开发态为脚本目录；打包后为 PyInstaller 解压目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def _fatal(msg: str) -> None:
    """弹出错误（无控制台时用户仍能看到原因）。"""
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, msg, "520 浪漫空间", 0x10)
            return
        except Exception:
            pass
    print(msg, file=sys.stderr)


def _cleanup_old_staging() -> None:
    """删除此前运行留下的临时页面目录。"""
    tmp_root = Path(tempfile.gettempdir())
    for old in tmp_root.glob(f"{_TEMP_PREFIX}*"):
        if old.is_dir():
            shutil.rmtree(old, ignore_errors=True)


def _stage_to_temp() -> Path:
    """
    把 index.html / css / js 复制到 %TEMP% 下的独立目录。
    Edge 子进程不会在 PyInstaller 解压目录被清理后丢失资源。
    """
    src = _bundle_dir()
    dest = Path(tempfile.mkdtemp(prefix=_TEMP_PREFIX))
    for name in ("index.html",):
        item = src / name
        if not item.is_file():
            raise FileNotFoundError(f"缺少资源: {item}")
        shutil.copy2(item, dest / name)
    for sub in ("css", "js"):
        sub_src = src / sub
        if not sub_src.is_dir():
            raise FileNotFoundError(f"缺少资源目录: {sub_src}")
        shutil.copytree(sub_src, dest / sub, dirs_exist_ok=True)
    # config.js 在 js 目录内，随 copytree 一并复制
    return dest


def _find_edge() -> str | None:
    """查找本机 Microsoft Edge。"""
    candidates = [
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe"),
    ]
    for path in candidates:
        if path and Path(path).is_file():
            return path
    return shutil.which("msedge")


def _find_chrome() -> str | None:
    """查找 Google Chrome。"""
    candidates = [
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    ]
    for path in candidates:
        if path and Path(path).is_file():
            return path
    return shutil.which("chrome")


def _open_app_mode(browser_exe: str, url: str) -> None:
    """以 --app 模式启动浏览器（独立窗口）。"""
    cmd = [
        browser_exe,
        f"--app={url}",
        "--new-window",
        "--window-size=1280,800",
        "--disable-features=EdgeSessionRestore",
    ]
    # 勿使用 CREATE_NO_WINDOW，否则可能导致 Edge/Chrome 窗口无法显示
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main() -> None:
    _cleanup_old_staging()
    staged = _stage_to_temp()
    url = (staged / "index.html").resolve().as_uri()

    edge = _find_edge()
    if edge:
        _open_app_mode(edge, url)
        return

    chrome = _find_chrome()
    if chrome:
        _open_app_mode(chrome, url)
        return

    opened = webbrowser.open(url, new=1)
    if not opened:
        _fatal(
            "未找到 Microsoft Edge 或 Chrome。\n"
            "Win10/11 通常自带 Edge，请确认已安装后重试。"
        )
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as err:
        _fatal(f"启动失败:\n{err}")
        raise SystemExit(1) from err
