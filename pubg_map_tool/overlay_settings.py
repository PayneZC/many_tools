# -*- coding: utf-8 -*-
"""覆盖层配置持久化（data/overlay_settings.json，按地图分别记录显示参数）。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

# 默认全局快捷键：显示/隐藏覆盖层（右 Ctrl + M）
DEFAULT_HOTKEY_TOGGLE = "ctrl_r+m"
STORE_VERSION = 2


@dataclass
class OverlayMapSettings:
    """单张地图的覆盖层显示参数（位置、透明度、比例等）。"""

    opacity: int = 70  # 透明度 15–100
    scale: int = 42  # 显示比例 15–120
    topmost: bool = True
    pos_x: int = -1  # -1 表示下次打开该地图时居中
    pos_y: int = -1

    def clamp(self) -> OverlayMapSettings:
        self.opacity = max(15, min(100, int(self.opacity)))
        self.scale = max(15, min(120, int(self.scale)))
        return self

    @classmethod
    def from_dict(cls, raw: dict) -> OverlayMapSettings:
        return cls(
            opacity=int(raw.get("opacity", 70)),
            scale=int(raw.get("scale", 42)),
            topmost=bool(raw.get("topmost", True)),
            pos_x=int(raw.get("pos_x", -1)),
            pos_y=int(raw.get("pos_y", -1)),
        ).clamp()


@dataclass
class OverlayGlobalSettings:
    """全局快捷键（所有地图共用）。"""

    hotkey_enabled: bool = True
    hotkey_toggle: str = DEFAULT_HOTKEY_TOGGLE

    def clamp(self) -> OverlayGlobalSettings:
        hk = (self.hotkey_toggle or DEFAULT_HOTKEY_TOGGLE).strip().lower()
        self.hotkey_toggle = hk if hk else DEFAULT_HOTKEY_TOGGLE
        return self

    @classmethod
    def from_dict(cls, raw: dict) -> OverlayGlobalSettings:
        return cls(
            hotkey_enabled=bool(raw.get("hotkey_enabled", True)),
            hotkey_toggle=str(raw.get("hotkey_toggle", DEFAULT_HOTKEY_TOGGLE)),
        ).clamp()


def settings_path(data_dir: Path) -> Path:
    return data_dir / "overlay_settings.json"


def _read_raw(data_dir: Path) -> dict:
    path = settings_path(data_dir)
    if not path.is_file():
        return {"version": STORE_VERSION, "global": {}, "maps": {}}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {"version": STORE_VERSION, "global": {}, "maps": {}}
        return _migrate_if_needed(raw)
    except (json.JSONDecodeError, OSError):
        return {"version": STORE_VERSION, "global": {}, "maps": {}}


def _migrate_if_needed(raw: dict) -> dict:
    """将旧版单文件配置迁移为按地图存储的结构。"""
    if raw.get("version") == STORE_VERSION:
        return raw
    # v1：顶层直接是 opacity / scale / hotkey 等字段
    legacy_map = OverlayMapSettings.from_dict(raw)
    legacy_global = OverlayGlobalSettings.from_dict(raw)
    return {
        "version": STORE_VERSION,
        "global": asdict(legacy_global.clamp()),
        "maps": {},
        "_default_map": asdict(legacy_map.clamp()),
    }


def _write_raw(data_dir: Path, store: dict) -> None:
    path = settings_path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    store["version"] = STORE_VERSION
    path.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")


def load_global_settings(data_dir: Path) -> OverlayGlobalSettings:
    store = _read_raw(data_dir)
    global_raw = store.get("global") or {}
    return OverlayGlobalSettings.from_dict(global_raw)


def save_global_settings(data_dir: Path, settings: OverlayGlobalSettings) -> None:
    store = _read_raw(data_dir)
    store["global"] = asdict(settings.clamp())
    _write_raw(data_dir, store)


def load_map_settings(data_dir: Path, map_id: str) -> OverlayMapSettings:
    """读取指定地图的覆盖层配置；无记录时使用迁移默认值或出厂默认。"""
    store = _read_raw(data_dir)
    maps = store.get("maps") or {}
    if map_id in maps and isinstance(maps[map_id], dict):
        return OverlayMapSettings.from_dict(maps[map_id])
    default_raw = store.get("_default_map")
    if isinstance(default_raw, dict):
        return OverlayMapSettings.from_dict(default_raw)
    return OverlayMapSettings()


def save_map_settings(data_dir: Path, map_id: str, settings: OverlayMapSettings) -> None:
    store = _read_raw(data_dir)
    if "maps" not in store or not isinstance(store["maps"], dict):
        store["maps"] = {}
    store["maps"][map_id] = asdict(settings.clamp())
    # 已有按地图记录后不再需要迁移用的默认快照
    store.pop("_default_map", None)
    _write_raw(data_dir, store)
