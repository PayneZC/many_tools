# -*- coding: utf-8 -*-
"""应用图标路径与窗口图标设置。"""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path


def resource_dir(app_dir: Path) -> Path:
    """开发目录或 PyInstaller 解压目录。"""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
    return app_dir


def icon_paths(app_dir: Path) -> tuple[Path, Path]:
    base = resource_dir(app_dir)
    return base / "app_icon.png", base / "app_icon.ico"


def apply_window_icon(window: tk.Tk | tk.Toplevel, app_dir: Path) -> None:
    png, ico = icon_paths(app_dir)
    if png.is_file():
        try:
            photo = tk.PhotoImage(file=str(png))
            window.iconphoto(True, photo)
            setattr(window, "_icon_photo_ref", photo)
        except tk.TclError:
            pass
    if ico.is_file():
        try:
            window.iconbitmap(str(ico))
        except tk.TclError:
            pass
