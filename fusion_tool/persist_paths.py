# -*- coding: utf-8 -*-
"""注释：融合工具数据目录与持久化路径（均位于程序执行目录下的 data）。"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


def app_dir() -> Path:
    """注释：脚本目录；打包后为 exe 所在目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def data_dir() -> Path:
    """注释：所有本地持久化数据的根目录。"""
    root = app_dir() / "data"
    root.mkdir(parents=True, exist_ok=True)
    return root


def recoil_presets_path() -> Path:
    """注释：压枪方案配置文件。"""
    return data_dir() / "recoil_presets.json"


def overlay_settings_path() -> Path:
    """注释：游戏覆盖层全局/分地图配置（与 pubg_map_tool 结构一致）。"""
    return data_dir() / "overlay_settings.json"


def configure_recoil_config_module() -> Path:
    """
    注释：将 recoil_config 的写入路径重定向到 data 目录。
    必须在首次调用 load_config / save_config 之前执行。
    """
    import recoil_config

    path = recoil_presets_path()
    recoil_config.CONFIG_PATH = path
    # 注释：兼容旧版写在程序根目录的配置，首次启动时复制到 data。
    legacy = app_dir() / "recoil_presets.json"
    if legacy.is_file() and not path.is_file():
        try:
            shutil.copy2(legacy, path)
        except OSError:
            pass
    return path
