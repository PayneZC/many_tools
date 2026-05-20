# -*- coding: utf-8 -*-
"""PyInstaller 运行时：DLL 搜索路径 + Tcl/Tk 库路径（tkinter 工具共用）。"""
import os
import sys

if getattr(sys, "frozen", False):
    base = getattr(sys, "_MEIPASS", "")
    if base:
        # 将打包的 DLL 目录加入搜索路径（Conda 的 ffi.dll、tcl86t.dll 等）
        if hasattr(os, "add_dll_directory"):
            try:
                os.add_dll_directory(base)
            except OSError:
                pass
        os.environ["PATH"] = base + os.pathsep + os.environ.get("PATH", "")
        tcl_dir = os.path.join(base, "tcl8.6")
        tk_dir = os.path.join(base, "tk8.6")
        if os.path.isdir(tcl_dir):
            os.environ["TCL_LIBRARY"] = tcl_dir
        if os.path.isdir(tk_dir):
            os.environ["TK_LIBRARY"] = tk_dir
