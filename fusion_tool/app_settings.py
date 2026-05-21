# -*- coding: utf-8 -*-
"""注释：融合工具全局设置（托盘、鼠标辅助快捷键等）。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from persist_paths import data_dir

# 注释：默认快捷键，用于切换鼠标辅助总开关。
DEFAULT_MOUSE_HOTKEY = "ctrl_r+f10"
SETTINGS_FILE = data_dir() / "app_settings.json"


@dataclass
class AppSettings:
    mouse_hotkey_enabled: bool = True
    mouse_hotkey_toggle: str = DEFAULT_MOUSE_HOTKEY

    def clamp(self) -> AppSettings:
        hk = (self.mouse_hotkey_toggle or DEFAULT_MOUSE_HOTKEY).strip().lower()
        self.mouse_hotkey_toggle = hk if hk else DEFAULT_MOUSE_HOTKEY
        return self

    @classmethod
    def from_dict(cls, data: dict) -> AppSettings:
        return cls(
            mouse_hotkey_enabled=bool(data.get("mouse_hotkey_enabled", False)),
            mouse_hotkey_toggle=str(data.get("mouse_hotkey_toggle", DEFAULT_MOUSE_HOTKEY)),
        ).clamp()


def load_app_settings() -> AppSettings:
    if not SETTINGS_FILE.is_file():
        cfg = AppSettings()
        save_app_settings(cfg)
        return cfg
    try:
        raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return AppSettings()
        return AppSettings.from_dict(raw)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return AppSettings()


def save_app_settings(cfg: AppSettings) -> None:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(
        json.dumps(asdict(cfg.clamp()), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
