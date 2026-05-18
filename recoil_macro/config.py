"""压枪方案配置的加载与持久化。"""

from __future__ import annotations

import json
import sys
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class RecoilPreset:
    """单条压枪方案：间隔与每步下移像素。"""

    id: str
    name: str
    interval_ms: float = 18.0
    move_pixels: int = 14

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> RecoilPreset:
        return cls(
            id=str(data.get("id") or uuid.uuid4().hex[:8]),
            name=str(data.get("name") or "未命名"),
            interval_ms=float(data.get("interval_ms", 18.0)),
            move_pixels=int(data.get("move_pixels", 14)),
        )


@dataclass
class RecoilConfigFile:
    """配置文件根结构。"""

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


def _runtime_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resolve_config_path() -> Path:
    """优先 exe/脚本同目录，不可写时回退用户目录。"""
    runtime_path = _runtime_base_dir() / "recoil_presets.json"
    try:
        runtime_path.parent.mkdir(parents=True, exist_ok=True)
        if not runtime_path.exists():
            runtime_path.write_text("{}", encoding="utf-8")
            runtime_path.unlink(missing_ok=True)
        return runtime_path
    except OSError:
        pass

    user_dir = Path.home() / ".many_tools" / "recoil_macro"
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir / "recoil_presets.json"


CONFIG_PATH = resolve_config_path()


def default_config() -> RecoilConfigFile:
    """内置默认方案，首次运行或文件损坏时使用。"""
    presets = [
        RecoilPreset("default", "默认", interval_ms=18.0, move_pixels=14),
        RecoilPreset("mild", "轻柔", interval_ms=22.0, move_pixels=10),
        RecoilPreset("strong", "强力", interval_ms=14.0, move_pixels=20),
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
