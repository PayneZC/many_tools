# -*- coding: utf-8 -*-
"""
PUBG.IM 地图目录定义。

数据来源：https://pubg.im/maps
开启「8x8 地图细节」时，部分地图使用 *_Detailed.avif（带点位的详细版）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

ASSETS_BASE = "https://assets.pubg.im"


@dataclass(frozen=True)
class MapEntry:
    """单张地图的元数据。"""

    id: str
    name_zh: str
    name_en: str
    asset_prefix: str  # 如 Erangel_Main
    has_detailed: bool

    def high_res_url(self, *, with_8x8: bool) -> str:
        """根据是否启用 8x8 细节返回下载 URL。"""
        if with_8x8 and self.has_detailed:
            return f"{ASSETS_BASE}/{self.asset_prefix}_High_Res_Detailed.avif"
        return f"{ASSETS_BASE}/{self.asset_prefix}_High_Res.avif"

    @property
    def display_name(self) -> str:
        return f"{self.name_zh} ({self.name_en})"


# 地图列表（与 pubg.im 一致）
MAP_CATALOG: tuple[MapEntry, ...] = (
    MapEntry("erangel", "艾伦格", "Erangel", "Erangel_Main", True),
    MapEntry("miramar", "米拉玛", "Miramar", "Miramar_Main", True),
    MapEntry("taego", "泰戈", "Taego", "Taego_Main", True),
    MapEntry("vikendi", "维寒迪", "Vikendi", "Vikendi_Main", True),
    MapEntry("rondo", "荣都", "Rondo", "Rondo_Main", True),
    MapEntry("deston", "帝斯顿", "Deston", "Deston_Main", True),
    MapEntry("sanhok", "萨诺", "Sanhok", "Sanhok_Main", False),
    MapEntry("karakin", "卡拉金", "Karakin", "Karakin_Main", False),
    MapEntry("paramo", "帕拉莫", "Paramo", "Paramo_Main", False),
    MapEntry("haven", "褐湾", "Haven", "Haven_Main", False),
    MapEntry("camp", "训练场", "Camp Jackal", "Camp_Jackal_Main", False),
)


def iter_maps() -> Iterable[MapEntry]:
    return MAP_CATALOG


def get_map(map_id: str) -> MapEntry | None:
    for m in MAP_CATALOG:
        if m.id == map_id:
            return m
    return None
