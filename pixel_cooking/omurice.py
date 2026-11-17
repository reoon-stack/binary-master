"""ピクセルアート料理ショート「何の料理かわかった？」(完成品: オムライス)

すべてコードで描画する。外部の画像・写真・絵文字は使わない。
  - 内部解像度 180x320 のドット絵を、ニアレストネイバーで 6 倍 → 1080x1920
  - 世界は縦長 (270 x 1440)。カメラが まな板 → コンロ → 盛り付け台 へなめらかにパンする
  - 音(包丁・炒め・焼き など ASMR)も numpy で合成する

構成 (30秒):
   0- 3s  暗い中をスポットライトが動き、食材の一部だけ見える
   3- 9s  手が玉ねぎ・鶏肉を包丁で刻み、まとめてフライパンへ落とす
   9-19s  炒める → ご飯 → ケチャップ → 混ぜる → 成形 / 隣で卵を割って焼く
  19-24s  フライパンごと皿へ運び、ご飯と卵を盛る(湯気で全体はまだ見えない)
  24-30s  湯気が晴れ、ケチャップを描いて完成。「何の料理かわかった？」

使い方:  python pixel_cooking/omurice.py out.mp4
"""

from __future__ import annotations

import math
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

LW, LH = 270, 480          # 描画する範囲(ワールド座標の1画面分)
CROP_X, CROP_Y = 45, 80    # そこから切り出す範囲(1.5倍ズーム)
VW, VH = 180, 320
SCALE = 6
W, H = VW * SCALE, VH * SCALE
FPS = 30
DURATION = 30.0
WORLD_H = 1440
SR = 44100

RNG = np.random.default_rng(20261118)
FONT_PATH = "/usr/share/fonts/opentype/unifont/unifont_jp.otf"

# ------------------------------------------------------------------ パレット
OUT = (62, 36, 28)          # 共通の濃い輪郭色
SKIN = (241, 194, 158)
SKIN_SH = (214, 156, 124)
SKIN_HI = (252, 218, 190)
SKIN_OUT = (112, 64, 48)
NAIL = (250, 222, 210)
SLEEVE = (205, 150, 72)
SLEEVE_SH = (170, 116, 52)
SLEEVE_OUT = (96, 60, 30)

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


def make_world() -> Image.Image:
    world = Image.new("RGBA", (LW, WORLD_H))
    counter = wood(LW, WORLD_H, (166, 112, 70), plank=24, seed=3).convert("RGBA")
    world.alpha_composite(counter)
    d = ImageDraw.Draw(world)

    # --- ゾーンA: まな板と小物
    board = Image.new("RGBA", (210, 310))
    bw = wood(210, 310, (226, 184, 128), plank=310, seed=5, vertical=True).convert("RGBA")
    mask = Image.new("L", (210, 310))
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, 209, 309), 12, fill=255)
    board.paste(bw, (0, 0), mask)
    bd = ImageDraw.Draw(board)
    bd.rounded_rectangle((7, 7, 202, 302), 9, outline=(200, 156, 100))
    bd.rounded_rectangle((8, 8, 201, 301), 8, outline=(238, 202, 150))
    bd.line((4, 300, 205, 300), fill=(196, 150, 96))
    board = add_outline(board, (104, 66, 36))
    paste_shadow(world, board, 30, 102, 3, 5, 90)
    paste(world, board, 30, 102)

    # 鉢植えのハーブ(左上)
    d.ellipse((2, 8, 40, 46), fill=(150, 82, 52), outline=OUT)
    d.ellipse((6, 12, 36, 42), fill=(96, 62, 40))
    for i in range(14):
        a = i / 14 * math.tau
        cx, cy = 21 + 10 * math.cos(a), 27 + 10 * math.sin(a)
        d.ellipse((cx - 5, cy - 4, cx + 5, cy + 4), fill=(86, 150, 70), outline=(40, 80, 40))
        d.point((cx - 2, cy - 2), fill=(150, 210, 110))
    # 布巾(右下)
    d.rounded_rectangle((214, 418, 272, 478), 4, fill=(236, 230, 214), outline=OUT)
    for y in range(424, 476, 8):
        d.line((215, y, 271, y), fill=(196, 84, 70))

    # --- ゾーンB: コンロ
    d.rounded_rectangle((8, 500, 262, 952), 10, fill=(58, 56, 62), outline=(24, 22, 26))
    d.rounded_rectangle((12, 504, 258, 948), 8, outline=(88, 86, 94))
    for (cx, cy, r) in ((135, 640, 66), (150, 800, 42)):
        d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(30, 30, 34), width=3)
        for a in range(0, 360, 60):
            x2, y2 = cx + (r + 10) * math.cos(math.radians(a)), cy + (r + 10) * math.sin(math.radians(a))
            d.line((cx + (r - 30) * math.cos(math.radians(a)), cy + (r - 30) * math.sin(math.radians(a)),
                    x2, y2), fill=(30, 30, 34), width=3)
        d.ellipse((cx - 10, cy - 10, cx + 10, cy + 10), fill=(40, 40, 46), outline=(20, 20, 24))
    for kx in (60, 110, 160, 210):
        d.ellipse((kx - 8, 924, kx + 8, 940), fill=(196, 196, 204), outline=(30, 30, 34))
        d.line((kx, 926, kx, 932), fill=(60, 60, 66), width=2)

    # --- ゾーンC: ランチョンマットと皿
    mat = Image.new("RGBA", (240, 240))
    md = ImageDraw.Draw(mat)
    for gy in range(0, 240, 12):
        for gx in range(0, 240, 12):
            a, b = (gx // 12) % 2, (gy // 12) % 2
            col = (238, 232, 220) if a == b == 0 else (206, 92, 80) if a == b == 1 else (226, 160, 148)
            md.rectangle((gx, gy, gx + 11, gy + 11), fill=col)
    md.rectangle((0, 0, 239, 239), outline=(150, 60, 50))
    paste_shadow(world, mat, 15, PLATE_C[1] - 120, 2, 3, 60)
    paste(world, mat, 15, PLATE_C[1] - 120)
    plate = make_plate()
    paste_shadow(world, plate, PLATE_C[0] - 86, PLATE_C[1] - 86, 4, 6, 90)
    paste(world, plate, PLATE_C[0] - 86, PLATE_C[1] - 86)
    # スプーン
    sp = Image.new("RGBA", (16, 90))
    sd = ImageDraw.Draw(sp)
    sd.ellipse((2, 0, 13, 20), fill=(214, 216, 224))
    sd.ellipse((4, 3, 9, 12), fill=(244, 246, 250))
    sd.rounded_rectangle((6, 18, 9, 88), 2, fill=(196, 198, 208))
    sd.line((7, 22, 7, 84), fill=(236, 238, 244))
    sp = add_outline(sp, (70, 70, 84))
    paste_shadow(world, sp, 226, PLATE_C[1] - 40, 2, 3, 70)
    paste(world, sp, 226, PLATE_C[1] - 40)
    return world


def make_plate() -> Image.Image:
    R = 86
    D = 2 * R
    p = Image.new("RGBA", (D, D))
    d = ImageDraw.Draw(p)
    d.ellipse((0, 0, D - 1, D - 1), fill=(246, 246, 242), outline=(140, 140, 154))
    d.ellipse((2, 4, D - 3, D - 1), outline=(220, 220, 224))
    d.ellipse((16, 16, D - 17, D - 17), outline=(214, 214, 220))
    d.ellipse((18, 19, D - 19, D - 19), fill=(250, 250, 248))
    for i in range(32):
        a = i / 32 * math.tau
        x, y = R + (R - 8) * math.cos(a), R + (R - 8) * math.sin(a)
        d.rectangle((x - 1, y - 1, x + 1, y + 1), fill=(84, 118, 186))
    d.arc((24, 24, 110, 110), 200, 250, fill=(255, 255, 255), width=2)
    return p


# ------------------------------------------------------------------ 食材スプライト


def onion_sprite() -> Image.Image:
    s = Image.new("RGBA", (36, 32))
    d = ImageDraw.Draw(s)
    d.ellipse((0, 0, 35, 31), fill=(238, 228, 196))
    d.ellipse((2, 2, 33, 29), fill=(244, 236, 210))
    for k in (-10, -4, 3, 9):
        d.arc((17 + k - 14, 1, 17 + k + 14, 30), 250, 290, fill=(214, 198, 150))
        d.line((17 + k, 3, 17 + k, 28), fill=(224, 210, 168))
    d.ellipse((6, 5, 15, 11), fill=(252, 248, 232))
    d.rectangle((33, 13, 35, 18), fill=(190, 160, 100))
    return add_outline(s, (140, 118, 76))


def chicken_sprite() -> Image.Image:
    s = Image.new("RGBA", (40, 28))
    d = ImageDraw.Draw(s)
    d.ellipse((0, 4, 22, 27), fill=(234, 148, 140))
    d.ellipse((12, 0, 39, 24), fill=(236, 152, 144))
    d.ellipse((8, 6, 30, 26), fill=(238, 158, 150))
    for (x1, y1, x2, y2) in ((6, 10, 14, 14), (18, 6, 30, 9), (16, 18, 26, 22), (30, 14, 36, 16)):
        d.line((x1, y1, x2, y2), fill=(250, 226, 212), width=2)
    d.ellipse((14, 3, 22, 7), fill=(250, 196, 188))
    return add_outline(s, (150, 76, 70))


def egg_sprite() -> Image.Image:
    s = Image.new("RGBA", (14, 17))
    d = ImageDraw.Draw(s)
    d.ellipse((0, 0, 13, 16), fill=(248, 238, 220))
    d.ellipse((7, 6, 13, 16), fill=(230, 214, 190))
    d.ellipse((1, 1, 11, 14), fill=(250, 242, 226))
    d.ellipse((3, 3, 6, 6), fill=(255, 252, 244))
    return add_outline(s, (150, 124, 96))


# ------------------------------------------------------------------ 道具スプライト


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


def chopsticks_sprite() -> Image.Image:
    s = Image.new("RGBA", (12, 76))
    d = ImageDraw.Draw(s)
    d.line((3, 0, 4, 75), fill=(150, 92, 56), width=2)
    d.line((8, 0, 7, 75), fill=(150, 92, 56), width=2)
    d.line((3, 0, 3, 40), fill=(196, 140, 92))
    return add_outline(s, (60, 36, 24))


def bowl_sprite(fill: float) -> Image.Image:
    s = Image.new("RGBA", (46, 46))
    d = ImageDraw.Draw(s)
    d.ellipse((0, 0, 45, 45), fill=(242, 240, 234))
    d.ellipse((4, 4, 41, 41), fill=(214, 220, 232))
    for i in range(16):
        a = i / 16 * math.tau
        d.point((23 + 21 * math.cos(a), 23 + 21 * math.sin(a)), fill=(70, 100, 170))
    r = 17 * math.sqrt(max(0.0, fill))
    if r > 1:
        d.ellipse((23 - r, 23 - r, 23 + r, 23 + r), fill=(246, 244, 236))
        rng = np.random.default_rng(5)
        for _ in range(int(60 * fill)):
            a, rr = rng.uniform(0, math.tau), r * math.sqrt(rng.random())
            d.point((23 + rr * math.cos(a), 23 + rr * math.sin(a)), fill=(222, 220, 210))
    return add_outline(s, (90, 90, 110))


def bottle_sprite() -> Image.Image:
    s = Image.new("RGBA", (22, 64))
    d = ImageDraw.Draw(s)
    d.polygon([(9, 0), (13, 0), (14, 8), (8, 8)], fill=(240, 236, 226))
    d.rounded_rectangle((5, 8, 17, 14), 2, fill=(240, 236, 226))
    d.rounded_rectangle((1, 14, 21, 63), 6, fill=(204, 40, 36))
    d.line((4, 18, 4, 58), fill=(236, 96, 84))
    d.rectangle((3, 30, 19, 44), fill=(244, 232, 200))
    d.line((6, 35, 16, 35), fill=(60, 140, 60))
    d.line((6, 39, 14, 39), fill=(204, 40, 36))
    return add_outline(s, (90, 20, 20))


def pan_sprite(r: int, handle_dir: tuple[float, float], handle_len: int) -> tuple[Image.Image, tuple]:
    """フライパン(上から)。戻り値: (sprite, (中心x, 中心y, 取っ手先x, 取っ手先y)) すべて sprite 内座標"""
    pad = handle_len + 6
    size = 2 * (r + pad)
    s = Image.new("RGBA", (size, size))
    d = ImageDraw.Draw(s)
    c = size // 2
    hx, hy = handle_dir
    sx, sy = c + hx * (r - 4), c + hy * (r - 4)
    ex, ey = c + hx * (r + handle_len), c + hy * (r + handle_len)
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
    d.line((cuff[0], cuff[1], ax, ay), fill=SLEEVE_OUT, width=26)
    d.line((cuff[0], cuff[1], ax, ay), fill=SLEEVE, width=23)
    # 袖の影と編み目
    px, py = -uy, ux
    d.line((cuff[0] + px * 8, cuff[1] + py * 8, ax + px * 8, ay + py * 8), fill=SLEEVE_SH, width=4)
    for k in range(0, int(ln), 5):
        cx, cy = cuff[0] + ux * k, cuff[1] + uy * k
        if k < 10:
            d.line((cx - px * 10, cy - py * 10, cx + px * 10, cy + py * 10), fill=SLEEVE_SH)
        elif k % 10 == 0:
            d.point((cx - px * 4, cy - py * 4), fill=SLEEVE_SH)


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


# ------------------------------------------------------------------ 食材の動き

BOARD_ONION0 = (95, 215)
ONION_C = (128, 232)
CHICK0 = (80, 335)
CHICK_C = (126, 256)
EGG_BOARD = (214, 138)
ONION_PILE = (200, 168)
CHICK_PILE = (192, 246)
GATHER = (135, 386)
RICE_PAN0 = (135, 640)
EGG_PAN0 = (150, 800)
PLATE_C = (135, 1215)

ONION_CUT = (3.5, 5.6, 11)     # 開始, 終了, 回数
CHICK_CUT = (6.45, 7.7, 7)

STIRS = [(10.5, 12.3), (13.45, 14.2), (15.1, 15.85)]
STIR_SPEED = math.tau / 0.75


def stir_amount(t):
    return sum(clamp(t - a, 0, b - a) for a, b in STIRS) * STIR_SPEED


def stirring(t):
    for a, b in STIRS:
        if a <= t <= b:
            return (t - a) * STIR_SPEED
    return None


def cam_y(t):
    y = 480 * ease(t, 8.9, 10.1)
    y += 420 * ease(t, 19.0, 20.2)
    y += 60 * ease(t, 24.0, 25.0)
    return int(round(y))


def rice_pan_c(t):
    p = ease(t, 19.0, 20.2)
    c = lerp2(RICE_PAN0, (135, 1150), p)
    c = (c[0], c[1] - 12 * ease(t, 20.25, 20.55) + 12 * ease(t, 20.6, 20.9))
    q = ease(t, 20.8, 21.6)
    return (c[0] - 300 * q, c[1])


def egg_pan_c(t):
    """卵のフライパン。盛り付け時は(画面外を回って)右からスライドインする。"""
    if t < 20.2:
        return EGG_PAN0
    if t < 21.0:
        c = lerp2(EGG_PAN0, (340, EGG_PAN0[1]), prog(t, 20.2, 20.5))
        return lerp2(c, (340, 1160), prog(t, 20.5, 20.9))
    c = lerp2((340, 1160), (148, 1160), ease(t, 21.0, 21.85))
    q = ease(t, 22.6, 23.4)
    return (c[0] + 300 * q, c[1])


def mound_c(t):
    pc = rice_pan_c(min(t, 20.25))
    return lerp2(pc, PLATE_C, ease(t, 20.25, 20.85))


class Piece:
    def __init__(self, kind, spawn, pile, pan_r, pan_a, mound_rel, k, size):
        self.kind, self.spawn, self.pile = kind, spawn, pile
        self.gather = (GATHER[0] + RNG.normal(0, 12), GATHER[1] + RNG.normal(0, 4))
        self.pan_r, self.pan_a, self.mound_rel, self.k, self.size = pan_r, pan_a, mound_rel, k, size
        self.fall_delay = RNG.uniform(0, 0.45)
        self.wob = RNG.uniform(0, math.tau)


def make_pieces():
    pieces = []
    for kind, n, c, (w, h), pile, size in (("onion", 34, ONION_C, (34, 30), ONION_PILE, 3),
                                           ("chicken", 22, CHICK_C, (38, 26), CHICK_PILE, 4)):
        for _ in range(n):
            a, rr = RNG.uniform(0, math.tau), math.sqrt(RNG.random())
            spawn = (c[0] + 0.4 * w * rr * math.cos(a), c[1] + 0.4 * h * rr * math.sin(a))
            pl = (pile[0] + RNG.normal(0, 7), pile[1] + RNG.normal(0, 5))
            mr = RNG.uniform(0, math.tau), math.sqrt(RNG.random())
            pieces.append(Piece(kind, spawn, pl, RNG.uniform(6, 50), RNG.uniform(0, math.tau),
                                (36 * mr[1] * math.cos(mr[0]), 20 * mr[1] * math.sin(mr[0])),
                                RNG.uniform(0.18, 0.4), size))
    return pieces


def make_grains(n=260):
    grains = []
    for _ in range(n):
        mr = RNG.uniform(0, math.tau), math.sqrt(RNG.random())
        grains.append(dict(r=RNG.uniform(2, 54), a=RNG.uniform(0, math.tau),
                           k=RNG.uniform(0.15, 0.4), t0=RNG.uniform(12.75, 13.15),
                           mix=RNG.uniform(0, 0.8), wob=RNG.uniform(0, math.tau),
                           rel=(38 * mr[1] * math.cos(mr[0]), 22 * mr[1] * math.sin(mr[0])),
                           vert=RNG.random() < 0.4))
    return grains


PIECES = make_pieces()
GRAINS = make_grains()

ONION_RAW, ONION_GOLD = (240, 236, 220), (216, 172, 96)
CHICK_RAW, CHICK_COOK = (236, 156, 146), (228, 196, 160)
RICE_WHITE, RICE_RED = (246, 244, 234), (214, 92, 58)


def pan_piece_pos(t, pan_r, pan_a, k, wob, rel, pc, shaping_p):
    s = stir_amount(t)
    ang = pan_a + s * k
    r = pan_r * (1 + 0.08 * math.sin(s * 0.7 + wob))
    p = (pc[0] + r * math.cos(ang), pc[1] + r * math.sin(ang) * 0.92)
    if shaping_p > 0:
        p = lerp2(p, (pc[0] + rel[0], pc[1] + rel[1]), shaping_p)
    return p


def piece_pos(pc: Piece, t):
    push_t = (5.6, 6.05) if pc.kind == "onion" else (7.7, 8.1)
    if t < push_t[0]:
        return None
    if t < 8.15:
        return lerp2(pc.spawn, pc.pile, ease(t, *push_t))
    if t < 8.8 + pc.fall_delay:
        return lerp2(pc.pile, pc.gather, ease(t, 8.15, 8.75))
    rp = rice_pan_c(t)
    target = pan_piece_pos(t, pc.pan_r, pc.pan_a, pc.k, pc.wob, pc.mound_rel,
                           rp, ease(t, 15.9, 16.4))
    if t >= 20.25:
        mc = mound_c(t)
        target = (mc[0] + pc.mound_rel[0], mc[1] + pc.mound_rel[1])
    fp = prog(t, 8.8 + pc.fall_delay, 9.75 + pc.fall_delay)
    if fp < 1:
        start = pc.gather
        x = lerp(start[0], target[0], smooth(fp))
        y = lerp(start[1], target[1], fp * fp)
        return (x, y)
    return target


def onion_color(t):
    return lerpc(ONION_RAW, ONION_GOLD, ease(t, 10.4, 13.0))


def chick_color(t):
    return lerpc(CHICK_RAW, CHICK_COOK, ease(t, 10.4, 12.6))


def rice_mix(t):
    return ease(t, 15.0, 16.0)


MOUND_RX, MOUND_RY = 48, 27

# ------------------------------------------------------------------ 湯気・油はね


def make_steam():
    parts = []
    for (a, b, rate, src, spread) in ((10.2, 20.4, 26, "rice", 46), (16.9, 21.9, 18, "egg", 34),
                                       (20.4, 25.6, 70, "plate", 70), (25.6, 30, 10, "plate", 40)):
        n = int((b - a) * rate)
        for _ in range(n):
            parts.append(dict(t0=RNG.uniform(a, b), src=src, dx=RNG.normal(0, spread / 2.2),
                              dy=RNG.normal(0, spread / 4), life=RNG.uniform(1.4, 2.4),
                              size=RNG.integers(2, 6), ph=RNG.uniform(0, math.tau),
                              big=src == "plate" and a < 25))
    return parts


STEAM = make_steam()


def steam_src(src, t):
    if src == "rice":
        return rice_pan_c(t)
    if src == "egg":
        return egg_pan_c(t)
    return PLATE_C


def draw_steam(dst, t, cy):
    ov = Image.new("RGBA", dst.size)
    d = ImageDraw.Draw(ov)
    fade_plate = 1 - ease(t, 24.2, 25.6) * 0.85
    for p in STEAM:
        age = t - p["t0"]
        if age < 0 or age > p["life"]:
            continue
        sx, sy = steam_src(p["src"], p["t0"])
        u = age / p["life"]
        x = sx + p["dx"] + 6 * math.sin(age * 2.2 + p["ph"])
        y = sy + p["dy"] - age * 22 - cy
        a = 95 * math.sin(math.pi * u)
        if p["src"] == "plate":
            a *= fade_plate * (1.5 if p["big"] else 1)
        a = int(min(150, a) // 30 * 30)
        if a <= 0:
            continue
        # ゆらゆら昇る細い湯気の筋(1〜2px の点を S 字に並べる)
        n = 4 + p["size"]
        w = 2 if p["big"] else 1
        for k in range(n):
            fk = k / n
            px = x + 2.2 * math.sin(fk * 4 + age * 3 + p["ph"])
            py = y - k * 2
            ak = int(a * (1 - abs(fk - 0.4)) // 30 * 30)
            if ak > 0:
                ix, iy = int(round(px)), int(round(py))
                d.rectangle((ix, iy, ix + w - 1, iy + 1), fill=(255, 255, 255, ak))
    # 盛り付け中は湯気のベールで料理の全体像を隠す
    v = ease(t, 22.2, 22.9) * (1 - ease(t, 24.1, 25.3))
    if v > 0:
        for i in range(8):
            ph = i * 1.7
            bx = PLATE_C[0] + 26 * math.sin(t * 0.7 + ph) + (i - 3.5) * 7
            by = PLATE_C[1] - cy + 2 + 12 * math.sin(t * 0.5 + ph * 1.3) - (t * 6 + i * 7) % 26
            rx, ry = 46 + 8 * math.sin(ph), 20 + 4 * math.cos(ph)
            a = int(v * 120 // 20 * 20)
            if a > 0:
                d.ellipse((bx - rx, by - ry, bx + rx, by + ry), fill=(255, 252, 246, a))
    dst.alpha_composite(ov)


def draw_sizzle(d, t, center, cy, radius, active):
    if not active:
        return
    rng = np.random.default_rng(int(t * FPS) * 7 + int(center[1]))
    for _ in range(5):
        a, rr = rng.uniform(0, math.tau), rng.uniform(0.3, 1.0) * radius
        x, y = center[0] + rr * math.cos(a), center[1] + rr * math.sin(a) - cy
        d.point((x, y), fill=(255, 250, 210))
    # 炎のちらつき
    for i in range(18):
        a = i / 18 * math.tau + t * 0.6
        if rng.random() < 0.6:
            r2 = radius + 18 + rng.integers(0, 3)
            x, y = center[0] + r2 * math.cos(a), center[1] + r2 * math.sin(a) - cy
            d.point((x, y), fill=(90, 150, 255) if rng.random() < 0.7 else (255, 200, 90))


# ------------------------------------------------------------------ 描画本体

ONION = onion_sprite()
CHICKEN = chicken_sprite()
EGG = egg_sprite()
KNIFE = knife_sprite()
SPATULA = spatula_sprite()
CHOP = chopsticks_sprite()
BOTTLE = bottle_sprite()
RICE_PAN, RICE_PAN_PTS = pan_sprite(78, (-0.5, 0.866), 52)
EGG_PAN, EGG_PAN_PTS = pan_sprite(52, (0.5, 0.866), 44)
FONT16 = ImageFont.truetype(FONT_PATH, 16)


def chop_state(t, cut):
    """(knife_x の割合 0→1, 持ち上げ量 0..1, 切った回数)"""
    a, b, n = cut
    if t < a:
        return 0.0, 1.0, 0
    p = prog(t, a, b)
    k = min(n, int(p * n))
    phase = (p * n) % 1
    lift = abs(math.cos(phase * math.pi)) if p < 1 else 1.0
    return k / n + (1 / n) * smooth(clamp(phase * 2 - 0.2)) * (p < 1), lift, k


def draw_sliced(dst, spr, cx, cy, frac, ncuts_done, ncuts_total, cam):
    """右端から frac の割合まで切られた食材。切れた部分は薄切りが少しずつずれる。"""
    w = spr.width
    x0, y0 = cx - w / 2, cy - spr.height / 2 - cam
    cut_x = int(w * (1 - frac))
    if cut_x > 0:
        paste(dst, spr.crop((0, 0, cut_x, spr.height)), x0, y0)
    edges = [int(w * (1 - j / ncuts_total)) for j in range(ncuts_done + 1)]
    for j in range(ncuts_done):
        xr, xl = edges[j], max(cut_x, edges[j + 1])
        if xr - xl <= 0:
            continue
        sl = spr.crop((xl, 0, xr, spr.height))
        off = 1 + (ncuts_done - j) * 0.55
        paste(dst, sl, x0 + xl + off, y0)
        d = ImageDraw.Draw(dst)
        d.line((x0 + xl + off, y0 + 3, x0 + xl + off, y0 + spr.height - 4), fill=(255, 255, 248))
    return x0 + cut_x


def draw_piece(d, kind, x, y, col, size):
    x, y = int(round(x)), int(round(y))
    dark = tuple(int(c * 0.78) for c in col)
    d.rectangle((x, y, x + size - 1, y + size - 1), fill=col)
    d.line((x, y + size - 1, x + size - 1, y + size - 1), fill=dark)
    d.line((x + size - 1, y, x + size - 1, y + size - 1), fill=dark)
    if kind == "chicken" and size > 3:
        d.point((x, y), fill=tuple(min(255, c + 18) for c in col))


def draw_egg_disk(dst, t, c, cam, morph):
    d = ImageDraw.Draw(dst)
    x, y = c[0], c[1] - cam
    if t < 16.8:
        return
    if t < 17.15:
        p = ease(t, 16.8, 17.15)
        r = lerp(8, 30, p)
        d.ellipse((x - r, y - r, x + r, y + r), fill=(246, 244, 236), outline=(220, 214, 200))
        d.ellipse((x - 7, y - 7, x + 7, y + 7), fill=(252, 184, 40), outline=(220, 140, 30))
        d.point((x - 3, y - 3), fill=(255, 236, 160))
        return
    w = ease(t, 17.15, 18.2)
    r = lerp(30, 47, ease(t, 17.15, 18.0))
    if morph <= 0:
        base = lerpc((246, 236, 200), (250, 206, 76), w)
        edge = lerpc((220, 210, 180), (232, 172, 60), w)
        d.ellipse((x - r, y - r, x + r, y + r), fill=base, outline=edge)
        if w < 1:
            for i in range(5):
                a = i * 1.3 + t * 5
                d.arc((x - r * 0.6, y - r * 0.6, x + r * 0.6, y + r * 0.6),
                      math.degrees(a), math.degrees(a) + 40, fill=(252, 184, 40), width=2)
        setp = ease(t, 18.3, 19.0)
        if setp > 0:
            d.ellipse((x - r + 3, y - r + 3, x + r - 3, y + r - 3),
                      outline=lerpc(base, (240, 180, 70), setp))
            rng = np.random.default_rng(int(t * 6))
            for _ in range(int(6 * setp)):
                a, rr = rng.uniform(0, math.tau), rng.uniform(0, r - 6)
                d.point((x + rr * math.cos(a), y + rr * math.sin(a)), fill=(255, 236, 150))
        return
    draw_omelet(dst, x, y, morph)


def draw_omelet(dst, x, y, morph):
    """フライパンの円(r=47) → ご飯の上のドーム型(rx=52, ry=30) へ変形。"""
    d = ImageDraw.Draw(dst)
    rx, ry = lerp(47, 52, morph), lerp(47, 30, morph)
    d.ellipse((x - rx - 1, y - ry - 1 + 3 * morph, x + rx + 1, y + ry + 1 + 3 * morph),
              fill=(196, 128, 36))
    d.ellipse((x - rx, y - ry, x + rx, y + ry), fill=(232, 164, 44))
    d.ellipse((x - rx + 2, y - ry + 1, x + rx - 4, y + ry - 4), fill=(248, 198, 64))
    d.ellipse((x - rx * 0.7 - 4, y - ry * 0.7 - 4, x + rx * 0.55, y + ry * 0.4),
              fill=(252, 216, 104))
    d.ellipse((x - rx * 0.55, y - ry * 0.65, x - rx * 0.15, y - ry * 0.4), fill=(255, 238, 170))
    if morph > 0.5:
        for s in (-1, 1):
            d.arc((x + s * rx * 0.72 - 8, y - 10, x + s * rx * 0.72 + 8, y + 10),
                  90 + s * 60, 270 + s * 60, fill=(222, 156, 44))


KETCHUP_PATH = [(-36, -4), (-24, 8), (-12, -9), (0, 7), (12, -9), (24, 8), (36, -4)]


def ketchup_points(p):
    pts = KETCHUP_PATH
    total = len(pts) - 1
    seg = p * total
    out = [pts[0]]
    for i in range(1, len(pts)):
        if i <= seg:
            out.append(pts[i])
        else:
            f = seg - (i - 1)
            if f > 0:
                out.append(lerp2(pts[i - 1], pts[i], f))
            break
    return out


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


def render_frame(world: Image.Image, t: float) -> Image.Image:
    cy = cam_y(t)
    img = world.crop((0, cy, LW, cy + LH))
    d = ImageDraw.Draw(img)

    # --- まな板の上の卵
    if cy < 300:
        paste_shadow(img, EGG, EGG_BOARD[0] - 7, EGG_BOARD[1] - 8 - cy, 2, 2, 60)
        paste(img, EGG, EGG_BOARD[0] - 7, EGG_BOARD[1] - 8 - cy)

    # --- 玉ねぎ
    ofrac, olift, ok = chop_state(t, ONION_CUT)
    onion_c = lerp2(BOARD_ONION0, ONION_C, ease(t, 3.15, 3.5))
    knife = None
    if t < 5.65:
        paste_shadow(img, ONION, onion_c[0] - 18, onion_c[1] - 16 - cy, 2, 2, 60)
        cutx = draw_sliced(img, ONION, onion_c[0], onion_c[1], ofrac, ok, ONION_CUT[2], cy)
        if t >= 3.0:
            knife = (cutx + 1, onion_c[1] - 12, olift if t >= ONION_CUT[0] else 1.0)
    # --- 鶏肉
    cfrac, clift, ck = chop_state(t, CHICK_CUT)
    chick_c = lerp2(CHICK0, CHICK_C, ease(t, 6.1, 6.45))
    if t < 7.75:
        paste_shadow(img, CHICKEN, chick_c[0] - 20, chick_c[1] - 14 - cy, 2, 2, 60)
        cutx = draw_sliced(img, CHICKEN, chick_c[0], chick_c[1], cfrac, ck, CHICK_CUT[2], cy)
        if 6.05 <= t:
            knife = (cutx + 1, chick_c[1] - 14, clift if t >= CHICK_CUT[0] else 1.0)

    # --- フライパン2つ(運ぶ途中は、持ち上げている方を上に描く)
    rp = rice_pan_c(t)
    ep = egg_pan_c(t)

    def draw_pan(pan, pts, c):
        x0, y0 = c[0] - pts[0], c[1] - pts[1] - cy
        if -300 < y0 < LH + 50:
            paste_shadow(img, pan, x0, y0, 3, 4, 80)
            paste(img, pan, x0, y0)

    def rice_group():
        if t < 21.7:
            draw_pan(RICE_PAN, RICE_PAN_PTS, rp)
            draw_sizzle(d, t, rp, cy, 60, 9.8 < t < 19.0)
        draw_rice_contents()

    def egg_group():
        draw_pan(EGG_PAN, EGG_PAN_PTS, ep)
        draw_sizzle(d, t, ep, cy, 40, 16.85 < t < 19.0)
        draw_egg()

    def draw_rice_contents():
        # --- 皿の上のご飯(成形後)
        shaping = ease(t, 15.9, 16.4)
        mc = rice_pan_c(t) if t < 20.25 else mound_c(t)
        if t >= 20.25:
            mc = (mc[0], mc[1] + 5 * ease(t, 20.3, 20.85))
        if shaping > 0:
            col = lerpc(RICE_WHITE, RICE_RED, rice_mix(t))
            rx, ry = MOUND_RX * shaping, MOUND_RY * shaping
            d.ellipse((mc[0] - rx - 1, mc[1] - ry - cy, mc[0] + rx + 1, mc[1] + ry + 2 - cy),
                      fill=tuple(int(c * 0.8) for c in col))
            d.ellipse((mc[0] - rx, mc[1] - ry - cy, mc[0] + rx, mc[1] + ry - cy), fill=col)

        # --- 食材のかけら
        for pc in PIECES:
            pos = piece_pos(pc, t)
            if pos is None:
                continue
            col = onion_color(t) if pc.kind == "onion" else chick_color(t)
            if pc.kind == "chicken" and t > 11.5 and pc.wob > 3:
                col = lerpc(col, (196, 140, 88), ease(t, 11.5, 13.0))
            draw_piece(d, pc.kind, pos[0], pos[1] - cy, col, pc.size)

        # --- ご飯粒
        if t >= 12.75:
            bowl_tip = (rp[0] + 34, rp[1] - 36)
            for g in GRAINS:
                if t < g["t0"]:
                    continue
                target = pan_piece_pos(t, g["r"], g["a"], g["k"], g["wob"], g["rel"], rp,
                                       ease(t, 15.9, 16.4))
                if t >= 20.25:
                    target = (mc[0] + g["rel"][0], mc[1] + g["rel"][1])
                fp = prog(t, g["t0"], g["t0"] + 0.35)
                pos = lerp2(bowl_tip, target, fp) if fp < 1 else target
                mix = clamp((rice_mix(t) - g["mix"] * 0.4) / 0.6)
                col = lerpc(RICE_WHITE, RICE_RED, mix)
                x, y = int(pos[0]), int(pos[1] - cy)
                if g["vert"]:
                    d.line((x, y, x, y + 1), fill=col)
                else:
                    d.line((x, y, x + 1, y), fill=col)

        # --- ケチャップのかたまり(混ぜる前)
        kp = ease(t, 14.45, 14.9)
        if kp > 0 and t < 16.0:
            fade = 1 - ease(t, 15.1, 15.9)
            r = 10 * kp * fade
            if r > 0.5:
                kx, ky = rp[0] - 6, rp[1] - 4 - cy
                d.ellipse((kx - r, ky - r * 0.8, kx + r, ky + r * 0.8), fill=(190, 30, 30),
                          outline=(130, 16, 16))
                d.point((kx - r * 0.4, ky - r * 0.4), fill=(244, 110, 100))

    def draw_egg():
        # --- 卵
        morph = ease(t, 21.95, 22.6)
        egg_c = ep if t < 21.95 else lerp2(egg_pan_c(21.95), PLATE_C, morph)
        if t >= 16.8:
            draw_egg_disk(img, t, egg_c, cy, morph if t >= 21.95 else 0)

    if t < 20.9:
        egg_group()
        rice_group()
    else:
        rice_group()
        egg_group()

    # --- ケチャップの線(完成)
    kq = ease(t, 25.4, 26.8)
    if kq > 0:
        pts = [(PLATE_C[0] + x, PLATE_C[1] + y - cy) for x, y in ketchup_points(kq)]
        if len(pts) >= 2:
            d.line(pts, fill=(120, 14, 14), width=5, joint="curve")
            d.line(pts, fill=(196, 30, 30), width=3, joint="curve")
            d.line([(x - 1, y - 1) for x, y in pts], fill=(236, 92, 84), width=1)

    # --- 付け合わせのパセリ(盛り付け後)
    gp = ease(t, 22.9, 23.3)
    if gp > 0:
        gx, gy = PLATE_C[0] + 50, PLATE_C[1] + 26 - cy
        for (ox, oy) in ((0, 0), (3, -2), (-2, 2), (2, 3), (5, 1), (-1, -3)):
            if (ox + oy) % 3 < 3 * gp:
                d.rectangle((gx + ox - 1, gy + oy - 1, gx + ox + 1, gy + oy + 1), fill=(64, 140, 56))
                d.point((gx + ox, gy + oy - 1), fill=(130, 200, 96))
        d.line((gx - 3, gy + 5, gx + 1, gy + 1), fill=(90, 150, 70))

    # --- 道具と手
    # 左手: 玉ねぎ・鶏肉を押さえる / フライパンを持つ
    if 3.0 <= t < 6.0:
        enter = ease(t, 3.0, 3.25)
        out = ease(t, 5.55, 5.95)
        tx = onion_c[0] - 14 - (34 * ofrac) * 0.8
        g = lerp2((20, cy + 520), (tx, onion_c[1] + 6), enter)
        g = lerp2(g, (-10, cy + 540), out)
        draw_hand(img, "L", "claw", g[0], g[1], cy)
    if 6.0 <= t < 8.1:
        enter = ease(t, 6.0, 6.2)
        out = ease(t, 7.65, 8.05)
        tx = chick_c[0] - 16 - (38 * cfrac) * 0.8
        g = lerp2((20, cy + 520), (tx, chick_c[1] + 6), enter)
        g = lerp2(g, (-10, cy + 540), out)
        draw_hand(img, "L", "claw", g[0], g[1], cy)
    if 9.8 <= t < 21.7 or (19.0 <= t < 21.7):
        hx, hy = rp[0] - RICE_PAN_PTS[0] + RICE_PAN_PTS[2], rp[1] - RICE_PAN_PTS[1] + RICE_PAN_PTS[3]
        enter = ease(t, 9.8, 10.3)
        g = lerp2((10, cy + 560), (hx + 2, hy - 4), enter)
        draw_hand(img, "L", "grip", g[0], g[1], cy)

    # 右手: 包丁
    if 3.0 <= t < 9.4:
        if knife is not None and t < 7.7:
            kx, ky, lift = knife
        else:
            kx, ky, lift = CHICK_PILE[0] - 20, CHICK_PILE[1] - 30, 1.0
        if 5.6 <= t < 6.1:                                # 玉ねぎを寄せる
            kx, ky = lerp2((kx, ky), (ONION_PILE[0] - 22, ONION_PILE[1] - 10), ease(t, 5.6, 6.0))
        if 7.7 <= t:                                      # 鶏肉を寄せる→まとめる→下へ
            kx, ky = lerp2((chick_c[0] - 10, chick_c[1] - 14),
                           (CHICK_PILE[0] - 22, CHICK_PILE[1] - 12), ease(t, 7.7, 8.1))
            kx, ky = lerp2((kx, ky), (GATHER[0] + 24, GATHER[1] - 40), ease(t, 8.1, 8.75))
            kx, ky = lerp2((kx, ky), (300, cy + 560), ease(t, 8.8, 9.35))
        enter = ease(t, 3.0, 3.4)
        kx, ky = lerp2((240, cy + 540), (kx, ky), enter)
        up = 4 * lift
        ks = KNIFE
        paste(img, shadow_of(ks, 70), kx - 5 + 2 + up, ky - cy + 3 + up)
        paste(img, ks, kx - 5, ky - cy - up)
        draw_hand(img, "R", "grip", kx, ky + 56 - up, cy)

    # 右手: 木べら
    sa = stirring(t)
    shaping_active = 15.85 <= t <= 16.45
    if sa is not None or shaping_active:
        a = sa if sa is not None else t * 9
        rr = 26 if sa is not None else 10
        px, py = rp[0] + rr * math.cos(a), rp[1] + rr * 0.8 * math.sin(a)
        if shaping_active:
            py += 3 * math.sin(t * 22)
        paste(img, shadow_of(SPATULA), px - 9 + 3, py - cy - 9 + 4)
        paste(img, SPATULA, px - 9, py - cy - 9)
        draw_hand(img, "R", "grip", px, py + 55, cy)
    # 右手: 茶碗
    if 12.4 <= t < 13.45:
        enter, out = ease(t, 12.4, 12.7), ease(t, 13.15, 13.45)
        bx, by = rp[0] + 34, rp[1] - 36
        b = lerp2((260, cy + 520), (bx, by), enter)
        b = lerp2(b, (290, cy + 540), out)
        bowl = bowl_sprite(1 - ease(t, 12.75, 13.15))
        paste_shadow(img, bowl, b[0] - 23, b[1] - 23 - cy, 3, 4, 70)
        paste(img, bowl, b[0] - 23, b[1] - 23 - cy)
        draw_hand(img, "R", "grip", b[0] + 8, b[1] + 26, cy)
    # 右手: ケチャップ
    if 14.2 <= t < 15.15:
        enter, out = ease(t, 14.2, 14.42), ease(t, 14.9, 15.15)
        bx, by = rp[0] - 6, rp[1] - 4
        b = lerp2((260, cy + 520), (bx, by), enter)
        b = lerp2(b, (290, cy + 540), out)
        squeeze = 1 if 14.45 <= t <= 14.9 else 0
        paste_shadow(img, BOTTLE, b[0] - 11, b[1] - 2 - cy + 6, 3, 4, 70)
        paste(img, BOTTLE, b[0] - 11 + squeeze * (int(t * 30) % 2), b[1] - 2 - cy + 6)
        draw_hand(img, "R", "grip", b[0], b[1] + 44, cy)
    # 右手: 卵を割る
    if 16.2 <= t < 17.15:
        enter, out = ease(t, 16.2, 16.6), ease(t, 16.85, 17.15)
        ex, ey = ep[0], ep[1] - 6
        b = lerp2((260, cy + 520), (ex, ey), enter)
        b = lerp2(b, (300, cy + 560), out)
        split = ease(t, 16.68, 16.82)
        if split <= 0:
            paste(img, EGG, b[0] - 7, b[1] - 8 - cy)
        else:
            left = EGG.crop((0, 0, 7, 17))
            right = EGG.crop((7, 0, 14, 17))
            paste(img, left, b[0] - 7 - 5 * split, b[1] - 8 - cy)
            paste(img, right, b[0] + 5 * split, b[1] - 8 - cy)
        draw_hand(img, "R", "claw", b[0], b[1] + 12, cy)
    # 右手: 菜箸
    if 17.1 <= t < 18.7:
        enter, out = ease(t, 17.1, 17.3), ease(t, 18.35, 18.7)
        a = t * 13
        cx, cyy = ep[0] + 18 * math.cos(a), ep[1] + 14 * math.sin(a)
        b = lerp2((260, cy + 520), (cx, cyy), enter)
        b = lerp2(b, (300, cy + 560), out)
        paste(img, shadow_of(CHOP), b[0] - 6 + 3, b[1] - cy + 3)
        paste(img, CHOP, b[0] - 6, b[1] - cy)
        draw_hand(img, "R", "grip", b[0], b[1] + 52, cy)
    # 右手: 卵のフライパンを運ぶ
    if 20.9 <= t < 23.5:
        hx, hy = ep[0] - EGG_PAN_PTS[0] + EGG_PAN_PTS[2], ep[1] - EGG_PAN_PTS[1] + EGG_PAN_PTS[3]
        g = (hx - 2, hy - 4)
        draw_hand(img, "R", "grip", g[0], g[1], cy)
    # 右手: 仕上げのケチャップ
    if 25.0 <= t < 27.3:
        enter, out = ease(t, 25.0, 25.4), ease(t, 26.85, 27.3)
        tip = ketchup_points(max(kq, 0.001))[-1]
        bx, by = PLATE_C[0] + tip[0], PLATE_C[1] + tip[1]
        b = lerp2((260, cy + 520), (bx, by), enter)
        b = lerp2(b, (300, cy + 560), out)
        paste_shadow(img, BOTTLE, b[0] - 11, b[1] - cy + 2, 3, 4, 70)
        paste(img, BOTTLE, b[0] - 11, b[1] - cy + 2)
        draw_hand(img, "R", "grip", b[0], b[1] + 40, cy)

    draw_steam(img, t, cy)

    # ---- ここから画面座標(180x320)
    img = img.crop((CROP_X, CROP_Y, CROP_X + VW, CROP_Y + VH))
    arr = np.asarray(img.convert("RGB"), dtype=np.float32) * VIGNETTE
    # 冒頭: スポットライトで一部だけ見せる
    if t < 3.0:
        dark = 1 - ease(t, 2.35, 3.0)
        e = (EGG_BOARD[0] - 4, EGG_BOARD[1] + 4)
        o = (BOARD_ONION0[0] + 8, BOARD_ONION0[1] + 6)
        c = (CHICK0[0] + 12, CHICK0[1] - 4)
        sx, sy = lerp2(e, o, ease(t, 0.9, 1.25))
        sx, sy = lerp2((sx, sy), c, ease(t, 1.7, 2.05))
        yy, xx = np.mgrid[0:VH, 0:VW]
        dist = np.hypot(xx - (sx - CROP_X), yy - (sy - cy - CROP_Y))
        r = 20 + 2 * math.sin(t * 6)
        light = np.where(dist < r, 1.0, np.where(dist < r + 5, 0.55, 0.1))
        arr *= (1 - dark * (1 - light))[:, :, None]
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")

    if 0.25 <= t < 2.7:
        draw_text(img, ["なにができるかな？"], 34, 0.25, t, color=(255, 246, 220), panel=False)
    draw_text(img, ["何の料理か", "わかった？"], 30, 27.3, t)
    if t >= 27.5:
        sd = ImageDraw.Draw(img)
        rng = np.random.default_rng(int(t * 4))
        pcx, pcy = PLATE_C[0] - CROP_X, PLATE_C[1] - cy - CROP_Y
        for i in range(6):
            a = rng.uniform(0, math.tau)
            r = rng.uniform(70, 92)
            x, y = pcx + r * math.cos(a), pcy + r * 0.8 * math.sin(a)
            sz = 2 if (int(t * 8) + i) % 2 else 1
            sd.line((x - sz - 1, y, x + sz + 1, y), fill=(255, 250, 210))
            sd.line((x, y - sz - 1, x, y + sz + 1), fill=(255, 250, 210))
    return img.convert("RGB")


# ------------------------------------------------------------------ 音(ASMR)


def band_noise(n, lo, hi, seed):
    rng = np.random.default_rng(seed)
    x = rng.standard_normal(n)
    f = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(n, 1 / SR)
    f[(freqs < lo) | (freqs > hi)] = 0
    y = np.fft.irfft(f, n)
    return (y / (np.abs(y).max() + 1e-9)).astype(np.float32)


def env_ad(n, attack, decay):
    t = np.arange(n) / SR
    return np.minimum(1, t / max(attack, 1e-4)) * np.exp(-t / decay)


class Mixer:
    def __init__(self, seconds):
        self.buf = np.zeros(int(SR * seconds), dtype=np.float32)

    def add(self, sig, t, gain=1.0):
        i = int(t * SR)
        if i >= self.buf.size:
            return
        j = min(self.buf.size, i + sig.size)
        self.buf[i:j] += sig[: j - i] * gain


def chop_sound(seed):
    n = int(SR * 0.16)
    t = np.arange(n) / SR
    thunk = np.sin(2 * np.pi * (170 + 60 * np.exp(-t * 60)) * t) * np.exp(-t * 38)
    click = band_noise(n, 2500, 9000, seed) * np.exp(-t * 180)
    crunch = band_noise(n, 900, 5000, seed + 1) * np.exp(-t * 45) * 0.5
    return (thunk * 0.9 + click * 0.6 + crunch).astype(np.float32)


def scrape_sound(dur, seed):
    n = int(SR * dur)
    s = band_noise(n, 1500, 7000, seed)
    e = np.sin(np.linspace(0, np.pi, n)) ** 0.6
    return s * e * 0.25


def sizzle_track(total, intensity_fn, seed):
    n = int(SR * total)
    base = band_noise(n, 2500, 11000, seed) * 0.5 + band_noise(n, 600, 2500, seed + 1) * 0.15
    rng = np.random.default_rng(seed + 2)
    pops = np.zeros(n, dtype=np.float32)
    for i in rng.integers(0, n, int(total * 70)):
        ln = int(SR * rng.uniform(0.002, 0.008))
        pops[i:i + ln] += rng.uniform(0.3, 1.0) * np.exp(-np.arange(min(ln, n - i)) / (ln / 3))
    pops = pops * band_noise(n, 1500, 12000, seed + 3)
    times = np.arange(n) / SR
    inten = np.array([intensity_fn(x) for x in np.linspace(0, total, 600)])
    env = np.interp(times, np.linspace(0, total, 600), inten)
    am = 1 + 0.25 * band_noise(n, 2, 12, seed + 4)
    return ((base + pops * 1.4) * env * am).astype(np.float32)


def clank(seed, base=320):
    n = int(SR * 0.5)
    t = np.arange(n) / SR
    s = sum(np.sin(2 * np.pi * f * t) * a for f, a in ((base, 1), (base * 2.71, 0.5), (base * 4.4, 0.3)))
    return (s * np.exp(-t * 14) * 0.35 + band_noise(n, 2000, 8000, seed) * np.exp(-t * 90) * 0.2
            ).astype(np.float32)


def soft_thud(seed):
    n = int(SR * 0.25)
    t = np.arange(n) / SR
    return (np.sin(2 * np.pi * 110 * t) * np.exp(-t * 22) * 0.6
            + band_noise(n, 200, 1800, seed) * np.exp(-t * 30) * 0.3).astype(np.float32)


def chime(freqs, step=0.12):
    n = int(SR * (2.4 + step * len(freqs)))
    out = np.zeros(n, dtype=np.float32)
    for k, f in enumerate(freqs):
        t = np.arange(n - int(SR * k * step)) / SR
        s = (np.sin(2 * np.pi * f * t) + 0.3 * np.sin(4 * np.pi * f * t)) * np.exp(-t * 2.2)
        out[int(SR * k * step):] += s.astype(np.float32) * 0.25
    return out


def build_audio() -> np.ndarray:
    m = Mixer(DURATION)
    # 部屋の空気感
    m.add(band_noise(int(SR * DURATION), 80, 900, 1) * 0.035, 0)
    # 冒頭: やわらかいチャイム
    m.add(chime([523.25, 659.25, 783.99], 0.35) * 0.6, 0.15)

    # 包丁
    for (a, b, n), soft in ((ONION_CUT, 1.0), (CHICK_CUT, 0.8)):
        for k in range(n):
            tt = a + (b - a) * (k + 0.5) / n
            m.add(chop_sound(100 + k + int(a * 10)), tt, 0.55 * soft)
    m.add(soft_thud(3), 3.42, 0.5)
    m.add(soft_thud(4), 6.42, 0.5)
    for a, b in ((5.6, 6.05), (7.7, 8.1), (8.15, 8.75)):
        m.add(scrape_sound(b - a, int(a * 10)), a, 0.8)

    # ジュー(炒め)
    def sizzle_i(x):
        v = 0.0
        if x >= 9.1:
            v = 0.15 + 0.85 * ease(x, 9.1, 9.9)
        v *= 1 - 0.35 * ease(x, 10.8, 12.0)
        v += 0.45 * math.exp(-max(0, x - 12.8) * 2) * (x >= 12.8)        # ご飯
        v += 0.35 * math.exp(-max(0, x - 14.5) * 2) * (x >= 14.5)        # ケチャップ
        v += 0.9 * math.exp(-max(0, x - 16.85) * 1.6) * (x >= 16.85)     # 卵
        v += 0.25 * (16.85 <= x < 19.2)
        v *= 1 - ease(x, 19.2, 21.2)
        v += 0.3 * (20.4 <= x < 25.5) * (1 - ease(x, 24.3, 25.5))        # 皿の上のじゅわ
        return v
    m.add(sizzle_track(DURATION, sizzle_i, 7) * 1.4, 0)

    # 木べらで混ぜる(ヘラが鍋底をこする音)
    for a, b in STIRS:
        tt = a
        while tt < b:
            m.add(scrape_sound(0.28, int(tt * 100)), tt, 0.45)
            tt += 0.375
    # 成形のトントン
    for k in range(5):
        m.add(soft_thud(50 + k), 15.9 + k * 0.11, 0.3)
    # ご飯を入れる
    m.add(band_noise(int(SR * 0.5), 1500, 6000, 9) * np.hanning(int(SR * 0.5)) * 0.25, 12.75)
    # ケチャップ(ぶちゅっ)
    for tt in (14.5, 14.7):
        n = int(SR * 0.18)
        s = band_noise(n, 150, 900, int(tt * 10)) * np.sin(np.linspace(0, np.pi, n))
        m.add(s * 0.5, tt)
    # 卵を割る
    m.add(chop_sound(77) * 0.7, 16.68)
    n = int(SR * 0.05)
    m.add(band_noise(n, 3000, 10000, 78) * np.exp(-np.arange(n) / (SR * 0.01)) * 0.5, 16.72)
    # 菜箸のカチャカチャ
    tt = 17.15
    while tt < 18.35:
        n = int(SR * 0.03)
        m.add(band_noise(n, 3000, 9000, int(tt * 100)) * np.exp(-np.arange(n) / (SR * 0.006)) * 0.3, tt)
        tt += 0.12
    # 盛り付け
    m.add(clank(30, 300), 20.2, 0.6)
    m.add(soft_thud(31), 20.6, 0.7)
    m.add(scrape_sound(0.5, 32), 20.3, 0.5)
    m.add(clank(33, 360), 21.9, 0.5)
    m.add(scrape_sound(0.6, 34), 22.0, 0.45)
    m.add(soft_thud(35), 22.55, 0.6)
    # 仕上げケチャップ
    for tt in np.arange(25.45, 26.8, 0.22):
        n = int(SR * 0.15)
        s = band_noise(n, 150, 1000, int(tt * 100)) * np.sin(np.linspace(0, np.pi, n))
        m.add(s * 0.3, float(tt))
    # 完成のキラキラ
    m.add(chime([783.99, 987.77, 1174.66, 1567.98], 0.09) * 0.4, 27.3)
    sparkle = band_noise(int(SR * 2.5), 6000, 14000, 99) * np.exp(-np.arange(int(SR * 2.5)) / (SR * 0.8))
    m.add(sparkle * 0.06, 27.35)

    out = m.buf
    out /= max(1e-9, np.abs(out).max()) / 0.9
    fade = int(SR * 0.6)
    out[-fade:] *= np.linspace(1, 0, fade)
    out[: int(SR * 0.05)] *= np.linspace(0, 1, int(SR * 0.05))
    return out


def write_wav(path, x):
    pcm = (np.clip(x, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


# ------------------------------------------------------------------ 書き出し


def main(out_path: str, preview: list[float] | None = None):
    world = make_world()
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if preview:
        for t in preview:
            render_frame(world, t).resize((W, H), Image.NEAREST).save(out.parent / f"frame_{t:05.2f}.png")
        return
    wav = out.with_suffix(".wav")
    write_wav(wav, build_audio())
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", str(wav),
           "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p",
           "-tune", "animation", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
           "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-shortest",
           "-movflags", "+faststart", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    n = int(DURATION * FPS)
    for f in range(n):
        frame = render_frame(world, f / FPS).resize((W, H), Image.NEAREST)
        proc.stdin.write(frame.tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise SystemExit("ffmpeg failed")
    wav.unlink()
    print(f"wrote {out}")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[2] == "--preview":
        main(sys.argv[1], [float(x) for x in sys.argv[3:]])
    else:
        main(sys.argv[1] if len(sys.argv) > 1 else "omurice.mp4")
