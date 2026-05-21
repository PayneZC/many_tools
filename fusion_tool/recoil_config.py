# -*- coding: utf-8 -*-
"""注释：融合工具压枪方案配置（持久化至 data/recoil_presets.json）。"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

CONFIG_PATH = Path("recoil_presets.json")


@dataclass
class RecoilPreset:
    """
    单条压枪方案：
    - 第 1 次：first_move_pixels
    - 第 2 次起：increment_base_pixels + min(次数, increment_times) * increment_step_pixels
    """

    id: str
    name: str
    interval_ms: float = 18.0
    first_move_pixels: int = 28
    increment_base_pixels: int = 14
    increment_times: int = 8
    increment_step_pixels: int = 1

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> RecoilPreset:
        first = data.get("first_move_pixels")
        base = data.get("increment_base_pixels")
        times = data.get("increment_times", data.get("max_increment_count"))
        step = data.get("increment_step_pixels")
        if first is None:
            first = int(data.get("move_pixels", 28))
        if base is None:
            legacy = data.get("increment_move_pixels")
            base = int(legacy) if legacy is not None else 14
        if times is None:
            times = 8
        if step is None:
            step = 1
        return cls(
            id=str(data.get("id") or uuid.uuid4().hex[:8]),
            name=str(data.get("name") or "未命名"),
            interval_ms=float(data.get("interval_ms", 18.0)),
            first_move_pixels=max(1, int(first)),
            increment_base_pixels=max(0, int(base)),
            increment_times=max(1, int(times)),
            increment_step_pixels=max(0, int(step)),
        )


@dataclass
class RecoilConfigFile:
    active_preset_id: str = ""
    presets: list[RecoilPreset] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "active_preset_id": self.active_preset_id,
            "presets": [p.to_dict() for p in self.presets],
        }

    @classmethod
    def from_dict(cls, data: dict) -> RecoilConfigFile:
        presets = [RecoilPreset.from_dict(item) for item in data.get("presets", [])]
        return cls(
            active_preset_id=str(data.get("active_preset_id", "")),
            presets=presets,
        )


def move_pixels_for_tick(
    tick_index: int,
    first_move_pixels: int,
    increment_base_pixels: int,
    increment_times: int,
    increment_step_pixels: int,
) -> int:
    """注释：tick_index 为当次循环开始时的递增次数（从 0 起）。"""
    if tick_index <= 0:
        return max(1, first_move_pixels)
    count = min(tick_index, increment_times)
    return max(1, increment_base_pixels + count * increment_step_pixels)


def default_config() -> RecoilConfigFile:
    presets = [
        RecoilPreset("default", "默认", interval_ms=18.0, first_move_pixels=28, increment_base_pixels=14, increment_times=8, increment_step_pixels=1),
        RecoilPreset("mild", "轻柔", interval_ms=22.0, first_move_pixels=22, increment_base_pixels=10, increment_times=6, increment_step_pixels=1),
        RecoilPreset("strong", "强力", interval_ms=14.0, first_move_pixels=32, increment_base_pixels=16, increment_times=8, increment_step_pixels=2),
    ]
    return RecoilConfigFile(active_preset_id="default", presets=presets)


def load_config() -> RecoilConfigFile:
    if not CONFIG_PATH.exists():
        cfg = default_config()
        save_config(cfg)
        return cfg
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        cfg = RecoilConfigFile.from_dict(raw)
        if not cfg.presets:
            return default_config()
        if not cfg.active_preset_id or not any(p.id == cfg.active_preset_id for p in cfg.presets):
            cfg.active_preset_id = cfg.presets[0].id
        return cfg
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return default_config()


def save_config(cfg: RecoilConfigFile) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps(cfg.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def find_preset(cfg: RecoilConfigFile, preset_id: str) -> RecoilPreset | None:
    for preset in cfg.presets:
        if preset.id == preset_id:
            return preset
    return None


def new_preset_id() -> str:
    return uuid.uuid4().hex[:8]
