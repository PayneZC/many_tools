# -*- coding: utf-8 -*-
"""
从 pubg.im 资源站下载地图并转换为本地 PNG 数据源。
"""

from __future__ import annotations

import json
import shutil
import threading
import urllib.request
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from map_catalog import MapEntry, iter_maps

# 注册 AVIF 解码（若已安装 pillow-avif-plugin）
try:
    import pillow_avif  # noqa: F401
except ImportError:
    pass

from PIL import Image

ProgressCallback = Callable[[str, str], None]  # (map_id, message)


@dataclass
class StoredMapRecord:
    """manifest.json 中单条地图记录。"""

    id: str
    name_zh: str
    name_en: str
    has_detailed: bool
    with_8x8: bool
    source_url: str
    image_file: str
    updated_at: str
    file_size: int


@dataclass
class Manifest:
    version: int = 1
    source: str = "https://pubg.im/maps"
    with_8x8: bool = True
    updated_at: str = ""
    maps: list[StoredMapRecord] | None = None

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "source": self.source,
            "with_8x8": self.with_8x8,
            "updated_at": self.updated_at,
            "maps": [asdict(m) for m in (self.maps or [])],
        }

    @classmethod
    def from_dict(cls, data: dict) -> Manifest:
        # 忽略旧版 manifest 中的 thumb_file 等已废弃字段
        names = {f.name for f in fields(StoredMapRecord)}
        maps = [
            StoredMapRecord(**{k: v for k, v in raw.items() if k in names})
            for raw in data.get("maps", [])
        ]
        return cls(
            version=data.get("version", 1),
            source=data.get("source", "https://pubg.im/maps"),
            with_8x8=data.get("with_8x8", True),
            updated_at=data.get("updated_at", ""),
            maps=maps,
        )


class MapDataStore:
    """管理本地 data/maps 与 manifest.json。"""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.maps_dir = base_dir / "maps"
        self.manifest_path = base_dir / "manifest.json"

    def ensure_dirs(self) -> None:
        self.maps_dir.mkdir(parents=True, exist_ok=True)

    def cleanup_legacy_storage(self) -> None:
        """删除旧版 thumbs 目录，并清理 manifest 中已废弃的 thumb_file 字段。"""
        legacy = self.base_dir / "thumbs"
        if legacy.is_dir():
            shutil.rmtree(legacy, ignore_errors=True)
        if not self.manifest_path.is_file():
            return
        try:
            data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        dirty = False
        for item in data.get("maps", []):
            if isinstance(item, dict) and item.pop("thumb_file", None) is not None:
                dirty = True
        if dirty:
            self.manifest_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def load_manifest(self) -> Manifest:
        if not self.manifest_path.is_file():
            return Manifest(maps=[])
        try:
            data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            return Manifest.from_dict(data)
        except (json.JSONDecodeError, TypeError, KeyError):
            return Manifest(maps=[])

    def save_manifest(self, manifest: Manifest) -> None:
        self.ensure_dirs()
        self.manifest_path.write_text(
            json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def image_path(self, map_id: str) -> Path:
        return self.maps_dir / f"{map_id}.png"


def _download_bytes(url: str, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "PUBG-Map-Tool/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _save_avif_as_png(data: bytes, dest: Path) -> None:
    """将 AVIF 字节流转为 PNG 保存，便于 Tkinter 显示。"""
    from io import BytesIO

    dest.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(BytesIO(data)) as img:
        # 统一为 RGB，避免透明通道在部分控件上异常
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")
        img.save(dest, format="PNG", optimize=True)


def download_single_map(
    entry: MapEntry,
    store: MapDataStore,
    *,
    with_8x8: bool = True,
    on_progress: ProgressCallback | None = None,
) -> StoredMapRecord:
    """下载并保存一张地图，返回记录。"""

    def report(msg: str) -> None:
        if on_progress:
            on_progress(entry.id, msg)

    store.ensure_dirs()
    use_8x8 = with_8x8 and entry.has_detailed
    url = entry.high_res_url(with_8x8=use_8x8)
    image_dest = store.image_path(entry.id)

    report(f"正在下载: {entry.display_name}")
    image_data = _download_bytes(url)
    report("正在转换地图为 PNG…")
    _save_avif_as_png(image_data, image_dest)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    record = StoredMapRecord(
        id=entry.id,
        name_zh=entry.name_zh,
        name_en=entry.name_en,
        has_detailed=entry.has_detailed,
        with_8x8=use_8x8,
        source_url=url,
        image_file=image_dest.name,
        updated_at=now,
        file_size=image_dest.stat().st_size,
    )
    report("正在生成预览缓存…")
    try:
        from preview_cache import build_preview_file, preview_path

        build_preview_file(image_dest, preview_path(store.base_dir, entry.id))
    except OSError:
        pass  # 预览缓存失败不影响主流程

    report("完成")
    return record


def download_all_maps(
    store: MapDataStore,
    *,
    with_8x8: bool = True,
    on_progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> Manifest:
    """一键更新全部地图。"""
    records: list[StoredMapRecord] = []
    errors: list[str] = []

    for entry in iter_maps():
        if cancel_event and cancel_event.is_set():
            break
        try:
            rec = download_single_map(
                entry, store, with_8x8=with_8x8, on_progress=on_progress
            )
            records.append(rec)
        except Exception as exc:  # noqa: BLE001 — 收集错误继续下一张
            errors.append(f"{entry.id}: {exc}")
            if on_progress:
                on_progress(entry.id, f"失败: {exc}")

    # 与已有 manifest 合并，避免部分失败/取消时丢失未重下的地图记录
    existing = {m.id: m for m in (store.load_manifest().maps or [])}
    for rec in records:
        existing[rec.id] = rec

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest = Manifest(
        with_8x8=with_8x8,
        updated_at=now,
        maps=list(existing.values()),
    )
    if records:
        store.save_manifest(manifest)

    if errors and on_progress:
        on_progress("", "部分地图下载失败:\n" + "\n".join(errors))

    return manifest
