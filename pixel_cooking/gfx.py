"""ドット絵の共通部品: 補助関数・木目・道具・手と腕・器・文字。

内部解像度 180x320 (画面) / ワールドは 270 x 1440。最後に 6 倍して 1080x1920 にする。
"""

from __future__ import annotations

import math
import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

LW, LH = 270, 480          # ワールド座標で 1 画面ぶん描画する範囲
CROP_X, CROP_Y = 45, 80    # そこから切り出す範囲(1.5 倍ズーム)
VW, VH = 180, 320
SCALE = 6
W, H = VW * SCALE, VH * SCALE
FPS = 30
WORLD_H = 1440

FONT_CANDIDATES = [
    os.environ.get("PIXEL_FONT", ""),
    "/usr/share/fonts/opentype/unifont/unifont_jp.otf",
    "/usr/share/fonts/truetype/unifont/unifont_jp.ttf",
]

OUT = (62, 36, 28)
SKIN = (241, 194, 158)
SKIN_SH = (214, 156, 124)
SKIN_HI = (252, 218, 190)
SKIN_OUT = (112, 64, 48)
NAIL = (250, 222, 210)

# 回ごとに変える見た目 (Theme から設定)
STYLE = {"sleeve": ((205, 150, 72), (170, 116, 52), (96, 60, 30))}


def _font():
    for p in FONT_CANDIDATES:
        if p and Path(p).exists():
            return ImageFont.truetype(p, 16)
    raise RuntimeError("ドットフォント (unifont_jp) が見つかりません。fonts-unifont を入れてください")


FONT16 = _font()


# ------------------------------------------------------------------ 補助


def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def prog(t, a, b):
    return clamp((t - a) / (b - a)) if b > a else float(t >= a)


def smooth(p):
    return p * p * (3 - 2 * p)


def ease(t, a, b):
    return smooth(prog(t, a, b))


def lerp(a, b, p):
    return a + (b - a) * p


def lerp2(a, b, p):
    return (a[0] + (b[0] - a[0]) * p, a[1] + (b[1] - a[1]) * p)


def lerpc(c1, c2, p):
    return tuple(int(round(a + (b - a) * p)) for a, b in zip(c1, c2))


def add_outline(sprite: Image.Image, color) -> Image.Image:
    """不透明部分の外側 1px に輪郭を付ける。"""
    a = sprite.getchannel("A").point(lambda v: 255 if v > 0 else 0)
    grown = a.filter(ImageFilter.MaxFilter(3))
    ring = Image.new("RGBA", sprite.size, color + (255,))
    out = Image.new("RGBA", sprite.size)
    out.paste(ring, (0, 0), grown)
    out.alpha_composite(sprite)
    return out


def shadow_of(sprite: Image.Image, alpha=70) -> Image.Image:
    a = sprite.getchannel("A").point(lambda v: alpha if v > 0 else 0)
    s = Image.new("RGBA", sprite.size, (40, 20, 10, 0))
    s.putalpha(a)
    return s


def paste(dst: Image.Image, sprite: Image.Image, x: float, y: float):
    """sprite の左上を (x, y) に。整数に丸めてピクセルを揃える。"""
    dst.alpha_composite(sprite, (int(round(x)), int(round(y))))


def paste_shadow(dst, sprite, x, y, dx=3, dy=3, alpha=70):
    paste(dst, shadow_of(sprite, alpha), x + dx, y + dy)


# ------------------------------------------------------------------ 背景(世界)


def wood(w, h, base, plank=22, seed=1, vertical=False):
    rng = np.random.default_rng(seed)
    arr = np.zeros((h, w, 3), dtype=np.float32)
    n_planks = (h if not vertical else w) // plank + 2
    tones = rng.uniform(-14, 14, n_planks)
    for i in range(n_planks):
        sl = slice(i * plank, (i + 1) * plank)
        if vertical:
            arr[:, sl] = np.array(base) + tones[i]
        else:
            arr[sl, :] = np.array(base) + tones[i]
    # 木目: ゆらぐ横線
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(img)
    dark = tuple(int(c * 0.82) for c in base)
    light = tuple(min(255, int(c * 1.1)) for c in base)
    for _ in range(int(w * h / 260)):
        x, y = rng.integers(0, w), rng.integers(0, h)
        ln = int(rng.integers(8, 30))
        col = dark if rng.random() < 0.7 else light
        if vertical:
            d.line((x, y, x, y + ln), fill=col)
        else:
            d.line((x, y, x + ln, y), fill=col)
    for i in range(n_planks):
        p = i * plank
        seam = tuple(int(c * 0.6) for c in base)
        if vertical:
            d.line((p, 0, p, h), fill=seam)
        else:
            d.line((0, p, w, p), fill=seam)
    return img



# ------------------------------------------------------------------ 道具


def knife_sprite() -> Image.Image:
    s = Image.new("RGBA", (11, 66))
    d = ImageDraw.Draw(s)
    d.polygon([(1, 10), (5, 0), (9, 6), (9, 42), (1, 42)], fill=(184, 190, 202))
    d.line((2, 10, 2, 42), fill=(232, 236, 244))
    d.line((3, 6, 5, 1), fill=(232, 236, 244))
    d.line((8, 8, 8, 42), fill=(124, 130, 146))
    d.rectangle((1, 42, 9, 45), fill=(150, 152, 160))
    d.rounded_rectangle((2, 45, 8, 65), 2, fill=(86, 52, 34))
    d.line((3, 46, 3, 63), fill=(120, 76, 48))
    for y in (50, 58):
        d.point((5, y), fill=(220, 210, 190))
    return add_outline(s, (40, 36, 44))


def spatula_sprite() -> Image.Image:
    s = Image.new("RGBA", (18, 80))
    d = ImageDraw.Draw(s)
    d.rounded_rectangle((1, 0, 16, 20), 5, fill=(214, 168, 104))
    d.line((3, 2, 3, 17), fill=(236, 196, 140))
    d.rounded_rectangle((7, 18, 10, 79), 2, fill=(198, 150, 92))
    d.line((8, 20, 8, 76), fill=(226, 184, 128))
    return add_outline(s, (96, 60, 30))


def ladle_sprite() -> Image.Image:
    s = Image.new("RGBA", (22, 84))
    d = ImageDraw.Draw(s)
    d.ellipse((0, 0, 21, 21), fill=(196, 198, 208))
    d.ellipse((3, 3, 18, 18), fill=(150, 152, 164))
    d.arc((4, 4, 17, 17), 200, 260, fill=(236, 238, 244))
    d.rounded_rectangle((9, 19, 12, 83), 2, fill=(188, 190, 200))
    d.line((10, 22, 10, 80), fill=(232, 234, 240))
    return add_outline(s, (60, 60, 74))


def chopsticks_sprite() -> Image.Image:
    s = Image.new("RGBA", (12, 76))
    d = ImageDraw.Draw(s)
    d.line((3, 0, 4, 75), fill=(150, 92, 56), width=2)
    d.line((8, 0, 7, 75), fill=(150, 92, 56), width=2)
    d.line((3, 0, 3, 40), fill=(196, 140, 92))
    return add_outline(s, (60, 36, 24))


def bottle_sprite(body, label=(244, 232, 200), cap=(240, 236, 226)) -> Image.Image:
    s = Image.new("RGBA", (22, 64))
    d = ImageDraw.Draw(s)
    d.polygon([(9, 0), (13, 0), (14, 8), (8, 8)], fill=cap)
    d.rounded_rectangle((5, 8, 17, 14), 2, fill=cap)
    d.rounded_rectangle((1, 14, 21, 63), 6, fill=body)
    d.line((4, 18, 4, 58), fill=tuple(min(255, c + 60) for c in body))
    d.rectangle((3, 30, 19, 44), fill=label)
    d.line((6, 35, 16, 35), fill=(60, 140, 60))
    d.line((6, 39, 14, 39), fill=body)
    return add_outline(s, tuple(int(c * 0.45) for c in body))


def cup_sprite(liquid, fill: float) -> Image.Image:
    """計量カップ(上から)。中身の色と量。"""
    s = Image.new("RGBA", (40, 40))
    d = ImageDraw.Draw(s)
    d.ellipse((0, 4, 33, 37), fill=(222, 232, 240))
    d.ellipse((3, 7, 30, 34), fill=(196, 210, 222))
    r = 13 * math.sqrt(max(0.0, fill))
    if r > 1:
        d.ellipse((16 - r, 20 - r, 16 + r, 20 + r), fill=liquid)
        d.point((16 - r * 0.5, 20 - r * 0.5), fill=tuple(min(255, c + 50) for c in liquid))
    d.rounded_rectangle((31, 14, 39, 26), 3, outline=(196, 210, 222), width=3)
    return add_outline(s, (90, 104, 120))


def bowl_sprite(content, fill: float, speck=None) -> Image.Image:
    """材料を入れたボウル(上から)。"""
    s = Image.new("RGBA", (46, 46))
    d = ImageDraw.Draw(s)
    d.ellipse((0, 0, 45, 45), fill=(242, 240, 234))
    d.ellipse((4, 4, 41, 41), fill=(214, 220, 232))
    for i in range(16):
        a = i / 16 * math.tau
        d.point((23 + 21 * math.cos(a), 23 + 21 * math.sin(a)), fill=(70, 100, 170))
    r = 17 * math.sqrt(max(0.0, fill))
    if r > 1:
        d.ellipse((23 - r, 23 - r, 23 + r, 23 + r), fill=content)
        rng = np.random.default_rng(5)
        sp = speck or tuple(int(c * 0.88) for c in content)
        for _ in range(int(60 * fill)):
            a, rr = rng.uniform(0, math.tau), r * math.sqrt(rng.random())
            d.point((23 + rr * math.cos(a), 23 + rr * math.sin(a)), fill=sp)
    return add_outline(s, (90, 90, 110))


def vessel_sprite(kind: str, r: int, handle_dir, handle_len: int):
    """フライパン(黒)/片手鍋(銀・深い)。戻り値: (sprite, (cx, cy, 取っ手先x, 取っ手先y))"""
    pad = handle_len + 6
    size = 2 * (r + pad)
    s = Image.new("RGBA", (size, size))
    d = ImageDraw.Draw(s)
    c = size // 2
    hx, hy = handle_dir
    sx, sy = c + hx * (r - 4), c + hy * (r - 4)
    ex, ey = c + hx * (r + handle_len), c + hy * (r + handle_len)
    if kind == "pot":
        d.line((sx, sy, ex, ey), fill=(120, 122, 132), width=8)
        d.line((sx + hx * 22, sy + hy * 22, ex, ey), fill=(40, 38, 44), width=8)
        d.line((sx + hx * 22 - hy * 2, sy + hy * 22 + hx * 2, ex - hy * 2, ey + hx * 2),
               fill=(80, 78, 88), width=2)
        d.ellipse((c - r, c - r, c + r, c + r), fill=(150, 152, 164))
        d.ellipse((c - r + 3, c - r + 3, c + r - 3, c + r - 3), fill=(216, 218, 226))
        d.ellipse((c - r + 6, c - r + 6, c + r - 6, c + r - 6), fill=(120, 122, 134))
        d.ellipse((c - r + 12, c - r + 14, c + r - 10, c + r - 8), fill=(96, 98, 110))
        d.arc((c - r + 4, c - r + 4, c + r - 4, c + r - 4), 200, 270, fill=(246, 248, 252), width=2)
    else:
        d.line((sx, sy, ex, ey), fill=(30, 28, 32), width=10)
        d.line((sx + hx * 18, sy + hy * 18, ex, ey), fill=(96, 58, 36), width=8)
        d.line((sx + hx * 18 - hy * 2, sy + hy * 18 + hx * 2, ex - hy * 2, ey + hx * 2),
               fill=(132, 86, 54), width=2)
        d.ellipse((c - r, c - r, c + r, c + r), fill=(44, 44, 50))
        d.ellipse((c - r + 3, c - r + 3, c + r - 3, c + r - 3), fill=(92, 92, 102))
        d.ellipse((c - r + 6, c - r + 6, c + r - 6, c + r - 6), fill=(64, 64, 72))
        d.arc((c - r + 10, c - r + 10, c + r - 10, c + r - 10), 200, 260, fill=(104, 104, 116), width=2)
    s = add_outline(s, (20, 18, 22))
    return s, (c, c, ex, ey)


# ------------------------------------------------------------------ 器


def container_sprite(kind: str, accent=(84, 118, 186)) -> tuple[Image.Image, int]:
    """盛り付け用の器。戻り値: (sprite, 中に盛れる半径)"""
    if kind == "plate":
        R = 86
        p = Image.new("RGBA", (2 * R, 2 * R))
        d = ImageDraw.Draw(p)
        D = 2 * R
        d.ellipse((0, 0, D - 1, D - 1), fill=(246, 246, 242), outline=(140, 140, 154))
        d.ellipse((2, 4, D - 3, D - 1), outline=(220, 220, 224))
        d.ellipse((16, 16, D - 17, D - 17), outline=(214, 214, 220))
        d.ellipse((18, 19, D - 19, D - 19), fill=(250, 250, 248))
        for i in range(32):
            a = i / 32 * math.tau
            x, y = R + (R - 8) * math.cos(a), R + (R - 8) * math.sin(a)
            d.rectangle((x - 1, y - 1, x + 1, y + 1), fill=accent)
        d.arc((24, 24, 110, 110), 200, 250, fill=(255, 255, 255), width=2)
        return p, 62
    if kind == "soup_plate":
        R = 80
        p = Image.new("RGBA", (2 * R, 2 * R))
        d = ImageDraw.Draw(p)
        D = 2 * R
        d.ellipse((0, 0, D - 1, D - 1), fill=(246, 244, 238), outline=(140, 140, 154))
        d.ellipse((22, 22, D - 23, D - 23), fill=(226, 224, 218))
        d.ellipse((26, 28, D - 25, D - 23), fill=(240, 238, 232))
        d.ellipse((4, 4, D - 5, D - 5), outline=accent)
        return p, 50
    if kind == "donburi":
        R = 66
        p = Image.new("RGBA", (2 * R, 2 * R))
        d = ImageDraw.Draw(p)
        D = 2 * R
        d.ellipse((0, 0, D - 1, D - 1), fill=(236, 232, 222))
        for i in range(24):
            a = i / 24 * math.tau
            x, y = R + (R - 4) * math.cos(a), R + (R - 4) * math.sin(a)
            d.rectangle((x - 1, y - 1, x + 1, y + 1), fill=accent)
        d.ellipse((8, 8, D - 9, D - 9), fill=(208, 204, 196))
        d.ellipse((10, 12, D - 9, D - 9), fill=(226, 222, 214))
        return p, 50
    if kind == "owan":
        R = 58
        p = Image.new("RGBA", (2 * R, 2 * R))
        d = ImageDraw.Draw(p)
        D = 2 * R
        d.ellipse((0, 0, D - 1, D - 1), fill=(40, 26, 24))
        d.ellipse((5, 5, D - 6, D - 6), fill=(160, 36, 32))
        d.ellipse((8, 10, D - 7, D - 7), fill=(130, 26, 24))
        d.arc((4, 4, D - 5, D - 5), 200, 250, fill=(220, 120, 110), width=2)
        return p, 44
    # kobachi: 焼き物の小鉢
    R = 64
    p = Image.new("RGBA", (2 * R, 2 * R))
    d = ImageDraw.Draw(p)
    D = 2 * R
    d.ellipse((0, 0, D - 1, D - 1), fill=(168, 126, 86))
    rng = np.random.default_rng(3)
    for _ in range(120):
        a, rr = rng.uniform(0, math.tau), rng.uniform(R - 8, R - 1)
        d.point((R + rr * math.cos(a), R + rr * math.sin(a)), fill=(120, 86, 56))
    d.ellipse((8, 8, D - 9, D - 9), fill=(214, 200, 170))
    d.ellipse((10, 12, D - 9, D - 9), fill=(232, 222, 196))
    return add_outline(p, (80, 56, 36)), 46




# ------------------------------------------------------------------ 手


def hand_sprite(pose: str) -> Image.Image:
    """右手・甲が上・指先が上(画面奥)。手首 = (22,53)、握り位置 = (21,24)。"""
    s = Image.new("RGBA", (44, 56))
    d = ImageDraw.Draw(s)
    d.rectangle((14, 44, 30, 55), fill=SKIN)
    d.rounded_rectangle((11, 24, 33, 49), 7, fill=SKIN)
    if pose == "open":
        fingers = [(11, 6, 15), (17, 3, 21), (23, 5, 27), (29, 11, 32)]
        for x1, top, x2 in fingers:
            d.rounded_rectangle((x1, top, x2, 28), 2, fill=SKIN)
            d.rectangle((x1 + 1, top + 1, x2 - 1, top + 2), fill=NAIL)
            d.line((x1 + 1, top + 9, x2 - 1, top + 9), fill=SKIN_SH)
        d.line((13, 41, 5, 28), fill=SKIN, width=6)
        d.rectangle((4, 26, 6, 28), fill=NAIL)
    elif pose == "claw":
        fingers = [(11, 14, 15), (17, 12, 21), (23, 13, 27), (29, 17, 32)]
        for x1, top, x2 in fingers:
            d.rounded_rectangle((x1, top, x2, 28), 2, fill=SKIN)
            d.line((x1 + 1, top + 2, x2 - 1, top + 2), fill=SKIN_HI)
            d.line((x1 + 1, top + 6, x2 - 1, top + 6), fill=SKIN_SH)
        d.line((13, 42, 8, 33), fill=SKIN, width=6)
    else:  # grip(拳: 道具の柄が x≈21 を縦に通る)
        knuckles = [(11, 18, 15), (16, 16, 20), (21, 16, 25), (26, 18, 30)]
        for x1, top, x2 in knuckles:
            d.rounded_rectangle((x1, top, x2, 27), 2, fill=SKIN)
            d.line((x1 + 1, top + 1, x2 - 1, top + 1), fill=SKIN_HI)
        d.line((12, 26, 30, 26), fill=SKIN_SH)
        d.line((13, 42, 20, 30), fill=SKIN, width=6)
        d.line((14, 41, 20, 31), fill=SKIN_HI)
    # 影(右側)とハイライト
    a = np.array(s)
    alpha = a[:, :, 3] > 0
    for y in range(a.shape[0]):
        xs = np.where(alpha[y])[0]
        if xs.size:
            a[y, xs[-2:], :3] = SKIN_SH
    s = Image.fromarray(a)
    ImageDraw.Draw(s).line((15, 30, 15, 44), fill=SKIN_HI)
    return add_outline(s, SKIN_OUT)


HANDS = {p: hand_sprite(p) for p in ("open", "claw", "grip")}
HANDS_L = {p: im.transpose(Image.FLIP_LEFT_RIGHT) for p, im in HANDS.items()}
GRIP = (21, 24)
WRIST = (22, 53)


def draw_arm(dst: Image.Image, wrist, anchor):
    d = ImageDraw.Draw(dst)
    wx, wy = wrist
    ax, ay = anchor
    dx, dy = ax - wx, ay - wy
    ln = math.hypot(dx, dy) or 1
    ux, uy = dx / ln, dy / ln
    cuff = (wx + ux * 16, wy + uy * 16)
    d.line((wx, wy, cuff[0], cuff[1]), fill=SKIN_OUT, width=18)
    d.line((wx, wy, cuff[0], cuff[1]), fill=SKIN, width=15)
    sleeve, sleeve_sh, sleeve_out = STYLE["sleeve"]
    d.line((cuff[0], cuff[1], ax, ay), fill=sleeve_out, width=26)
    d.line((cuff[0], cuff[1], ax, ay), fill=sleeve, width=23)
    # 袖の影と編み目
    px, py = -uy, ux
    d.line((cuff[0] + px * 8, cuff[1] + py * 8, ax + px * 8, ay + py * 8), fill=sleeve_sh, width=4)
    for k in range(0, int(ln), 5):
        cx, cy = cuff[0] + ux * k, cuff[1] + uy * k
        if k < 10:
            d.line((cx - px * 10, cy - py * 10, cx + px * 10, cy + py * 10), fill=sleeve_sh)
        elif k % 10 == 0:
            d.point((cx - px * 4, cy - py * 4), fill=sleeve_sh)


def draw_hand(dst, side: str, pose: str, gx, gy, cam_y):
    """握り位置 (gx, gy:ワールド) に手を描く。腕は画面下から伸びる。"""
    spr = (HANDS if side == "R" else HANDS_L)[pose]
    gpx = GRIP[0] if side == "R" else spr.width - 1 - GRIP[0]
    wpx = WRIST[0] if side == "R" else spr.width - 1 - WRIST[0]
    x0, y0 = gx - gpx, gy - cam_y - GRIP[1]
    wrist = (x0 + wpx, y0 + WRIST[1])
    anchor = (236, CROP_Y + VH + 40) if side == "R" else (34, CROP_Y + VH + 40)
    # 影
    sh = Image.new("RGBA", dst.size)
    draw_arm(sh, (wrist[0], wrist[1]), anchor)
    paste(sh, spr, x0, y0)
    dst.alpha_composite(shadow_of(sh, 60), (4, 4))
    draw_arm(dst, wrist, anchor)
    paste(dst, spr, x0, y0)




def draw_text(dst, lines, top, t_in, t, color=(70, 40, 24), panel=True):
    if t < t_in:
        return
    p = prog(t, t_in, t_in + 0.45)
    bounce = (1 - p) ** 2 * -60 + math.sin(p * math.pi * 2) * 4 * (1 - p)
    d = ImageDraw.Draw(dst)
    d.fontmode = "1"
    tw = max(int(d.textlength(ln, font=FONT16)) for ln in lines)
    lh = 18
    x = (VW - tw) // 2
    y = int(top + bounce)
    if panel:
        hgt = lh * len(lines)
        d.rounded_rectangle((x - 12, y - 9, x + tw + 11, y + hgt + 6), 5, fill=(70, 40, 24))
        d.rounded_rectangle((x - 10, y - 7, x + tw + 9, y + hgt + 4), 4, fill=(252, 238, 206))
        d.rounded_rectangle((x - 8, y - 5, x + tw + 7, y + hgt + 2), 3, outline=(232, 204, 160))
    for i, ln in enumerate(lines):
        lx = (VW - int(d.textlength(ln, font=FONT16))) // 2
        ly = y + i * lh
        if not panel:
            for ox, oy in ((-1, 0), (1, 0), (0, -1), (0, 1), (1, 1)):
                d.text((lx + ox, ly + oy), ln, font=FONT16, fill=(30, 20, 16))
        d.text((lx, ly), ln, font=FONT16, fill=color)


def vignette():
    yy, xx = np.mgrid[0:VH, 0:VW]
    dx, dy = (xx - VW / 2) / (VW / 2), (yy - VH / 2) / (VH / 2)
    v = 1 - 0.22 * np.clip(dx ** 2 * 0.8 + dy ** 2 * 0.6, 0, 1.5)
    warm = np.stack([v * 1.02, v * 0.99, v * 0.93], axis=-1)
    return warm.astype(np.float32)


VIGNETTE = vignette()

