# -*- coding: utf-8 -*-
"""
生成 PUBG 地图工具图标：app_icon.png（界面）与 app_icon.ico（exe）。
运行：python generate_icons.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

TOOL_DIR = Path(__file__).resolve().parent
PNG_PATH = TOOL_DIR / "app_icon.png"
ICO_PATH = TOOL_DIR / "app_icon.ico"

# 与主程序配色一致
BG = (30, 30, 46)  # #1e1e2e
PANEL = (37, 37, 54)  # #252536
ACCENT = (137, 180, 250)  # #89b4fa
GRID = (70, 80, 110)
MUTED = (166, 173, 200)


def _draw_icon(size: int) -> Image.Image:
    """绘制 8x8 网格地图 + 准星图标。"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = max(2, size // 16)
    r = size // 2 - margin
    cx, cy = size // 2, size // 2
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=BG + (255,), outline=ACCENT + (255,), width=max(1, size // 32))

    inner = r - max(2, size // 20)
    x0, y0 = cx - inner, cy - inner
    x1, y1 = cx + inner, cy + inner
    draw.rectangle((x0, y0, x1, y1), fill=PANEL + (255,))

    # 8x8 网格
    grid_n = 8
    step_x = (x1 - x0) / grid_n
    step_y = (y1 - y0) / grid_n
    lw = max(1, size // 64)
    for i in range(1, grid_n):
        gx = int(x0 + i * step_x)
        gy = int(y0 + i * step_y)
        draw.line((gx, y0, gx, y1), fill=GRID + (180,), width=lw)
        draw.line((x0, gy, x1, gy), fill=GRID + (180,), width=lw)

    # 准星
    cr = max(2, size // 10)
    draw.ellipse((cx - cr, cy - cr, cx + cr, cy + cr), fill=ACCENT + (255,), outline=MUTED + (255,))
    arm = max(3, size // 8)
    aw = max(2, size // 40)
    draw.rectangle((cx - arm, cy - aw, cx + arm, cy + aw), fill=ACCENT + (230,))
    draw.rectangle((cx - aw, cy - arm, cx + aw, cy + arm), fill=ACCENT + (230,))

    return img


def main() -> None:
    base = _draw_icon(256)
    base.save(PNG_PATH, format="PNG")
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    icons = [base.resize(s, Image.Resampling.LANCZOS) for s in sizes]
    icons[0].save(
        ICO_PATH,
        format="ICO",
        sizes=[(i.width, i.height) for i in icons],
        append_images=icons[1:],
    )
    print(f"已生成: {PNG_PATH.name}, {ICO_PATH.name}")


if __name__ == "__main__":
    main()
