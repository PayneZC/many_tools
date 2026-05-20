# -*- coding: utf-8 -*-
"""
many_tools 各桌面工具共用的低调版权标识（大鹏Payne）。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

# 版权文案（各工具统一）
COPYRIGHT_TEXT = "© 大鹏Payne"

# 浅色主题：小字、浅灰，不抢眼
FG_LIGHT = "#9a9a9a"
# 深色主题（如 PUBG 地图工具）
FG_DARK = "#585b70"

FONT = ("Microsoft YaHei UI", 8)


def pack_copyright(parent: tk.Misc, *, dark: bool = False, **pack_kw: object) -> tk.Label:
    """在 parent 内 pack 一个右对齐的版权标签。"""
    fg = FG_DARK if dark else FG_LIGHT
    lbl = tk.Label(parent, text=COPYRIGHT_TEXT, font=FONT, fg=fg)
    defaults: dict[str, object] = {"side": tk.BOTTOM, "anchor": "e", "padx": 10, "pady": (0, 4)}
    defaults.update(pack_kw)
    lbl.pack(**defaults)  # type: ignore[arg-type]
    return lbl


def pack_copyright_ttk(parent: tk.Misc, *, dark: bool = False, **pack_kw: object) -> ttk.Label:
    """ttk 版版权标签，便于与 ttk 主题配色一致。"""
    fg = FG_DARK if dark else FG_LIGHT
    lbl = ttk.Label(parent, text=COPYRIGHT_TEXT, font=FONT, foreground=fg)
    defaults: dict[str, object] = {"side": tk.RIGHT, "padx": (8, 0)}
    defaults.update(pack_kw)
    lbl.pack(**defaults)  # type: ignore[arg-type]
    return lbl


def grid_copyright(
    parent: tk.Misc,
    row: int,
    *,
    column: int = 0,
    columnspan: int = 1,
    dark: bool = False,
    sticky: str = "e",
    **grid_kw: object,
) -> tk.Label:
    """在 grid 布局的指定行放置版权标签（默认右对齐）。"""
    fg = FG_DARK if dark else FG_LIGHT
    lbl = tk.Label(parent, text=COPYRIGHT_TEXT, font=FONT, fg=fg)
    defaults: dict[str, object] = {
        "row": row,
        "column": column,
        "columnspan": columnspan,
        "sticky": sticky,
        "padx": (0, 4),
        "pady": (2, 4),
    }
    defaults.update(grid_kw)
    lbl.grid(**defaults)  # type: ignore[arg-type]
    return lbl
