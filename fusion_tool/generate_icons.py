# -*- coding: utf-8 -*-
"""
生成 PUBG 辅助工具图标：小鸡造型 app_icon.png / app_icon.ico。
运行：python fusion_tool/generate_icons.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

TOOL_DIR = Path(__file__).resolve().parent
PNG_PATH = TOOL_DIR / "app_icon.png"
ICO_PATH = TOOL_DIR / "app_icon.ico"

# 与主程序暗色主题一致
BG = (30, 30, 46)
ACCENT = (137, 180, 250)
BODY = (250, 179, 63)
BODY_DARK = (230, 150, 45)
COMB = (220, 60, 70)
BEAK = (255, 140, 50)
EYE = (30, 30, 46)
FEET = (255, 120, 40)
CHEEK = (255, 120, 120)


def _draw_chicken(size: int) -> Image.Image:
    """绘制圆形底 + 卡通小鸡（鸡）图标。"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = max(2, size // 14)
    r = size // 2 - margin
    cx, cy = size // 2, size // 2 + size // 28

    # 背景圆
    draw.ellipse(
        (cx - r, cy - r, cx + r, cy + r),
        fill=BG + (255,),
        outline=ACCENT + (255,),
        width=max(1, size // 32),
    )

    # 身体（椭圆）
    bw = int(r * 0.72)
    bh = int(r * 0.62)
    by = cy + size // 18
    draw.ellipse((cx - bw, by - bh, cx + bw, by + bh), fill=BODY + (255,), outline=BODY_DARK + (255,), width=max(1, size // 48))

    # 翅膀
    wing_w = int(bw * 0.55)
    wing_h = int(bh * 0.45)
    wx = cx - int(bw * 0.15)
    draw.ellipse((wx - wing_w, by - wing_h, wx, by + wing_h // 2), fill=BODY_DARK + (220,))

    # 头
    hr = int(r * 0.36)
    hx, hy = cx + int(r * 0.08), by - bh - hr // 2
    draw.ellipse((hx - hr, hy - hr, hx + hr, hy + hr), fill=BODY + (255,), outline=BODY_DARK + (255,), width=max(1, size // 56))

    # 鸡冠（三个齿）
    comb_y = hy - hr - max(2, size // 40)
    tooth = max(2, size // 18)
    for dx in (-tooth, 0, tooth):
        px = hx + dx
        draw.polygon(
            (
                (px, comb_y - tooth * 2),
                (px - tooth, comb_y),
                (px + tooth, comb_y),
            ),
            fill=COMB + (255,),
        )

    # 眼睛
    eye_r = max(2, size // 28)
    ex = hx + hr // 3
    ey = hy - hr // 6
    draw.ellipse((ex - eye_r, ey - eye_r, ex + eye_r, ey + eye_r), fill=EYE + (255,))

    # 腮红
    cheek_r = max(1, size // 36)
    draw.ellipse((hx - hr // 2 - cheek_r, hy - cheek_r, hx - hr // 2 + cheek_r, hy + cheek_r), fill=CHEEK + (180,))

    # 喙
    beak_len = max(3, size // 12)
    draw.polygon(
        (
            (hx + hr - 2, hy),
            (hx + hr + beak_len, hy + beak_len // 3),
            (hx + hr - 2, hy + beak_len // 2),
        ),
        fill=BEAK + (255,),
    )

    # 脚
    foot_w = max(2, size // 16)
    foot_h = max(3, size // 14)
    fy = by + bh - foot_h // 2
    for fx in (cx - foot_w * 2, cx + foot_w):
        draw.rectangle((fx, fy, fx + foot_w, fy + foot_h), fill=FEET + (255,))

    return img


def main() -> None:
    base = _draw_chicken(256)
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
