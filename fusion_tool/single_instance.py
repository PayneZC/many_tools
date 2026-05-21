# -*- coding: utf-8 -*-
"""注释：Windows 单实例互斥，防止重复启动。"""

from __future__ import annotations

import ctypes
import sys

# 注释：全局唯一互斥量名称。
MUTEX_NAME = "ManyTools_PubgAssistTool_SingleInstance_v1"
ERROR_ALREADY_EXISTS = 183


def acquire_single_instance() -> int | None:
    """
    注释：获取单实例锁。
    返回 None 表示非 Windows；返回 0 表示已有实例；返回正整数为句柄。
    """
    if sys.platform != "win32":
        return None
    try:
        handle = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
        if not handle:
            return None
        if ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            ctypes.windll.kernel32.CloseHandle(handle)
            return 0
        return int(handle)
    except OSError:
        return None


def release_single_instance(handle: int | None) -> None:
    """注释：释放互斥量句柄。"""
    if sys.platform != "win32" or not handle:
        return
    try:
        ctypes.windll.kernel32.CloseHandle(handle)
    except OSError:
        pass
