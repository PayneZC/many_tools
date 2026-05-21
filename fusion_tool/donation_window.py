# -*- coding: utf-8 -*-
"""注释：打赏窗口，展示微信/支付宝收款码。"""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from PIL import Image, ImageTk

# 注释：与 main 一致的暗色主题色。
COLOR_BG = "#1e1e2e"
COLOR_PANEL = "#252536"
COLOR_ACCENT = "#89b4fa"
COLOR_TEXT = "#cdd6f4"
COLOR_MUTED = "#a6adc8"

ROOT_DIR = Path(__file__).resolve().parent.parent
SHARED_DIR = ROOT_DIR / "shared"
QR_MAX_EDGE = 260


def _asset_path(filename: str) -> Path:
    """注释：开发环境读 shared；打包后读 PyInstaller 解压目录。"""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            bundled = Path(meipass) / filename
            if bundled.is_file():
                return bundled
    return SHARED_DIR / filename


def _load_qr_photo(master: tk.Misc, path: Path) -> ImageTk.PhotoImage | None:
    """注释：缩放收款码以适配窗口。"""
    if not path.is_file():
        return None
    try:
        with Image.open(path) as img:
            im = img.convert("RGB")
            im.thumbnail((QR_MAX_EDGE, QR_MAX_EDGE), Image.Resampling.LANCZOS)
            return ImageTk.PhotoImage(im, master=master)
    except OSError:
        return None


class DonationWindow(tk.Toplevel):
    """注释：展示微信与支付宝收款码。"""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self.title("打赏支持")
        self.configure(bg=COLOR_BG)
        self.resizable(False, False)
        self.transient(master)
        self._photos: list[ImageTk.PhotoImage] = []

        header = tk.Frame(self, bg=COLOR_BG)
        header.pack(fill=tk.X, padx=16, pady=(12, 8))
        tk.Label(
            header,
            text="感谢您的支持",
            font=("Microsoft YaHei UI", 13, "bold"),
            fg=COLOR_ACCENT,
            bg=COLOR_BG,
        ).pack(anchor="w")
        tk.Label(
            header,
            text="若本工具对您有帮助，欢迎扫码打赏，您的支持是我持续更新的动力。",
            fg=COLOR_MUTED,
            bg=COLOR_BG,
            font=("Microsoft YaHei UI", 9),
            wraplength=520,
            justify=tk.LEFT,
        ).pack(anchor="w", pady=(6, 0))

        body = ttk.Frame(self, padding=(16, 8, 16, 16))
        body.pack(fill=tk.BOTH, expand=True)

        self._add_qr_column(body, "微信支付", _asset_path("wei.png"), 0)
        self._add_qr_column(body, "支付宝", _asset_path("zhi.jpg"), 1)

        self.update_idletasks()
        self.geometry(f"{max(self.winfo_reqwidth(), 560)}x{max(self.winfo_reqheight(), 420)}")

    def _add_qr_column(self, parent: ttk.Frame, title: str, path: Path, column: int) -> None:
        col = ttk.Frame(parent, padding=8)
        col.grid(row=0, column=column, padx=(0 if column == 0 else 12, 0), sticky=tk.N)
        tk.Label(
            col,
            text=title,
            font=("Microsoft YaHei UI", 11, "bold"),
            fg=COLOR_TEXT,
            bg=COLOR_BG,
        ).pack(pady=(0, 8))
        card = tk.Frame(col, bg=COLOR_PANEL, highlightthickness=1, highlightbackground="#45475a")
        card.pack()
        photo = _load_qr_photo(self, path)
        if photo is not None:
            self._photos.append(photo)
            tk.Label(card, image=photo, bg=COLOR_PANEL).pack(padx=12, pady=12)
        else:
            tk.Label(
                card,
                text=f"未找到收款码\n{path.name}",
                bg=COLOR_PANEL,
                fg=COLOR_MUTED,
                font=("Microsoft YaHei UI", 9),
                width=22,
                height=10,
            ).pack(padx=12, pady=12)
