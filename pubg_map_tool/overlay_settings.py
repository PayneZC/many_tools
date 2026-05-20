# -*- coding: utf-8 -*-
"""覆盖层配置持久化（保存至 data/overlay_settings.json）。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

# 默认全局快捷键：显示/隐藏覆盖层（右 Ctrl + M）
DEFAULT_HOTKEY_TOGGLE = "ctrl_r+m"


@dataclass
class OverlaySettings:
    """覆盖层控制参数。"""

    opacity: int = 70  # 透明度 15–100
    scale: int = 42  # 显示比例 15–120
    topmost: bool = True
    pos_x: int = -1  # -1 表示下次打开时居中
    pos_y: int = -1
    hotkey_enabled: bool = True
    hotkey_toggle: str = DEFAULT_HOTKEY_TOGGLE

    def clamp(self) -> OverlaySettings:
        self.opacity = max(15, min(100, int(self.opacity)))
        self.scale = max(15, min(120, int(self.scale)))
        hk = (self.hotkey_toggle or DEFAULT_HOTKEY_TOGGLE).strip().lower()
        self.hotkey_toggle = hk if hk else DEFAULT_HOTKEY_TOGGLE
        return self


def settings_path(data_dir: Path) -> Path:
    return data_dir / "overlay_settings.json"


def load_settings(data_dir: Path) -> OverlaySettings:
    path = settings_path(data_dir)
    if not path.is_file():
        return OverlaySettings()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        cfg = OverlaySettings(
            opacity=int(raw.get("opacity", 70)),
            scale=int(raw.get("scale", 42)),
            topmost=bool(raw.get("topmost", True)),
            pos_x=int(raw.get("pos_x", -1)),
            pos_y=int(raw.get("pos_y", -1)),
            hotkey_enabled=bool(raw.get("hotkey_enabled", True)),
            hotkey_toggle=str(raw.get("hotkey_toggle", DEFAULT_HOTKEY_TOGGLE)),
        )
        return cfg.clamp()
    except (json.JSONDecodeError, TypeError, ValueError):
        return OverlaySettings()


def save_settings(data_dir: Path, settings: OverlaySettings) -> None:
    path = settings_path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(settings.clamp()), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
