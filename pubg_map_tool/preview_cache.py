# -*- coding: utf-8 -*-
"""
预览图磁盘缓存：将 8K PNG 转为约 2048px 的 JPEG，切换地图时快速加载。
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

# 预览最长边（像素）；全图 8192 缩到此级别可显著降低内存与缩放开销
PREVIEW_MAX_EDGE = 2048
PREVIEW_JPEG_QUALITY = 82


def preview_dir(data_dir: Path) -> Path:
    d = data_dir / "previews"
    d.mkdir(parents=True, exist_ok=True)
    return d


def preview_path(data_dir: Path, map_id: str) -> Path:
    return preview_dir(data_dir) / f"{map_id}.jpg"


def _needs_rebuild(source_png: Path, cache_jpg: Path) -> bool:
    if not cache_jpg.is_file():
        return True
    try:
        return cache_jpg.stat().st_mtime < source_png.stat().st_mtime
    except OSError:
        return True


def build_preview_file(source_png: Path, cache_jpg: Path) -> None:
    """从原始 PNG 生成 JPEG 预览缓存。"""
    cache_jpg.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source_png) as img:
        # RGB 即可，减小体积；thumbnail 比 resize 更省内存
        im = img.convert("RGB")
        im.thumbnail((PREVIEW_MAX_EDGE, PREVIEW_MAX_EDGE), Image.Resampling.BILINEAR)
        im.save(cache_jpg, format="JPEG", quality=PREVIEW_JPEG_QUALITY, optimize=True)


def prebuild_missing_previews(data_dir: Path, image_paths: dict[str, Path]) -> None:
    """后台预生成缺失的预览缓存（已有本地地图时首次启动可调用）。"""
    for map_id, png in image_paths.items():
        if not png.is_file():
            continue
        cache_jpg = preview_path(data_dir, map_id)
        if not _needs_rebuild(png, cache_jpg):
            continue
        try:
            build_preview_file(png, cache_jpg)
        except OSError:
            continue


def load_preview_rgba(source_png: Path, map_id: str, data_dir: Path) -> Image.Image:
    """
    在后台线程中调用：返回用于界面预览的 RGBA 图（最长边 <= PREVIEW_MAX_EDGE）。
    优先读 JPEG 缓存，缺失或过期时从 PNG 重建。
    """
    cache_jpg = preview_path(data_dir, map_id)
    if _needs_rebuild(source_png, cache_jpg):
        build_preview_file(source_png, cache_jpg)

    with Image.open(cache_jpg) as img:
        return img.convert("RGBA")
