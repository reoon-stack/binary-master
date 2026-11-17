"""チャンネルのアイコン(800x800)とバナー(2560x1440)をドット絵で作る。

  python branding/make_branding.py                # 「ピコピコ堂」で作る
  python branding/make_branding.py --name 別の名前  # 名前を変えて作り直す

すべてコードで描画(外部素材なし)。小さく描いてニアレストネイバーで 8 倍に拡大する。
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pixel_cooking.gfx import FONT16, add_outline  # noqa: E402

OUT = (52, 30, 40)
CREAM = (255, 244, 222)
PINK = (255, 132, 150)
YELLOW = (255, 206, 84)
MINT = (110, 214, 190)
SKY = (120, 180, 255)
PURPLE = (150, 110, 220)


def text_sprite(text, color, scale=1, outline=OUT, shadow=True):
    d = ImageDraw.Draw(Image.new("L", (1, 1)))
    w = int(d.textlength(text, font=FONT16))
    s = Image.new("RGBA", (w + 4, 20))
    sd = ImageDraw.Draw(s)
    sd.fontmode = "1"
    sd.text((2, 1), text, font=FONT16, fill=color)
    if scale > 1:
        s = s.resize((s.width * scale, s.height * scale), Image.NEAREST)
    s = add_outline(s, outline)
    if shadow:
        sh = Image.new("RGBA", (s.width + 2, s.height + 2))
        a = s.getchannel("A").point(lambda v: 255 if v else 0)
        dark = Image.new("RGBA", s.size, OUT + (255,))
        sh.paste(dark, (2, 2), a)
        sh.alpha_composite(s, (0, 0))
        s = sh
    return s.crop(s.getbbox())


# ------------------------------------------------------------------ マスコット「ピコ」(レトロテレビ)

def mascot(blink=False, size=1):
    s = Image.new("RGBA", (64, 66))
    d = ImageDraw.Draw(s)
    # アンテナ
    d.line((24, 14, 16, 2), fill=(90, 80, 100), width=2)
    d.line((40, 14, 48, 2), fill=(90, 80, 100), width=2)
    d.ellipse((13, 0, 18, 5), fill=PINK)
    d.ellipse((46, 0, 51, 5), fill=YELLOW)
    # 本体
    d.rounded_rectangle((2, 12, 61, 58), 9, fill=(250, 150, 110))
    d.rounded_rectangle((2, 12, 61, 55), 9, fill=(255, 176, 128))
    d.line((10, 15, 52, 15), fill=(255, 214, 180))
    # 画面
    d.rounded_rectangle((8, 19, 46, 50), 6, fill=(40, 46, 70))
    d.rounded_rectangle((10, 21, 44, 48), 5, fill=(70, 200, 190))
    d.rounded_rectangle((10, 21, 44, 48), 5, outline=(40, 150, 150))
    for y in range(23, 47, 3):
        d.line((12, y, 42, y), fill=(84, 212, 200))
    d.line((13, 24, 20, 24), fill=(200, 255, 245))
    d.line((13, 25, 16, 25), fill=(200, 255, 245))
    # 顔
    if blink:
        d.line((18, 33, 22, 33), fill=OUT, width=2)
        d.line((32, 33, 36, 33), fill=OUT, width=2)
    else:
        d.rectangle((18, 30, 21, 35), fill=OUT)
        d.rectangle((33, 30, 36, 35), fill=OUT)
        d.point((19, 31), fill="white")
        d.point((34, 31), fill="white")
    d.rectangle((15, 37, 18, 38), fill=(255, 150, 170))
    d.rectangle((36, 37, 39, 38), fill=(255, 150, 170))
    d.line((24, 39, 26, 41), fill=OUT)
    d.line((26, 41, 28, 41), fill=OUT)
    d.line((28, 41, 30, 39), fill=OUT)
    # つまみとスピーカー
    d.ellipse((50, 22, 57, 29), fill=(90, 80, 100))
    d.point((53, 23), fill=(200, 200, 210))
    d.ellipse((50, 32, 57, 39), fill=(90, 80, 100))
    for y in (43, 46, 49):
        d.line((50, y, 57, y), fill=(220, 120, 90))
    # 足
    d.rectangle((10, 58, 15, 63), fill=(90, 80, 100))
    d.rectangle((48, 58, 53, 63), fill=(90, 80, 100))
    s = add_outline(s, OUT)
    if size > 1:
        s = s.resize((s.width * size, s.height * size), Image.NEAREST)
    return s


# ------------------------------------------------------------------ いろいろなジャンルの小物

def prop(kind):
    s = Image.new("RGBA", (24, 24))
    d = ImageDraw.Draw(s)
    if kind == "pan":
        d.ellipse((1, 4, 16, 19), fill=(60, 60, 70))
        d.ellipse((3, 6, 14, 17), fill=(90, 90, 100))
        d.ellipse((5, 8, 12, 15), fill=(250, 250, 240))
        d.ellipse((7, 10, 10, 13), fill=YELLOW)
        d.line((15, 15, 22, 21), fill=(130, 80, 50), width=3)
    elif kind == "quiz":
        d.rectangle((2, 2, 21, 21), fill=YELLOW)
        d.rectangle((2, 2, 21, 4), fill=(255, 236, 160))
        d.rectangle((2, 19, 21, 21), fill=(220, 150, 40))
        for x, y in ((3, 3), (19, 3), (3, 19), (19, 19)):
            d.point((x, y), fill=(160, 100, 30))
        d.text((8, 3), "?", font=FONT16, fill=(160, 90, 20))
    elif kind == "pad":
        d.rounded_rectangle((1, 7, 22, 18), 5, fill=PURPLE)
        d.rectangle((5, 11, 9, 12), fill=OUT)
        d.rectangle((6, 10, 7, 14), fill=OUT)
        d.ellipse((14, 9, 16, 11), fill=PINK)
        d.ellipse((17, 12, 19, 14), fill=YELLOW)
    elif kind == "bulb":
        d.ellipse((4, 1, 19, 16), fill=(255, 240, 140))
        d.ellipse((7, 4, 11, 8), fill="white")
        d.rectangle((8, 16, 15, 21), fill=(170, 170, 180))
        d.line((8, 18, 15, 18), fill=(120, 120, 130))
    elif kind == "note":
        d.rectangle((14, 2, 16, 16), fill=OUT)
        d.line((16, 2, 21, 6), fill=OUT, width=2)
        d.ellipse((7, 13, 16, 20), fill=SKY)
    elif kind == "star":
        pts = []
        for i in range(10):
            r = 11 if i % 2 == 0 else 5
            a = -math.pi / 2 + i * math.pi / 5
            pts.append((12 + r * math.cos(a), 12 + r * math.sin(a)))
        d.polygon(pts, fill=YELLOW)
        d.point((10, 8), fill="white")
    elif kind == "heart":
        d.ellipse((2, 4, 12, 14), fill=PINK)
        d.ellipse((11, 4, 21, 14), fill=PINK)
        d.polygon([(3, 11), (20, 11), (11.5, 21)], fill=PINK)
        d.point((6, 7), fill="white")
    elif kind == "clap":
        d.rectangle((3, 9, 20, 21), fill=(60, 60, 70))
        d.polygon([(3, 3), (20, 6), (20, 9), (3, 9)], fill=(240, 240, 240))
        for x in (6, 11, 16):
            d.line((x, 4, x + 2, 8), fill=(60, 60, 70), width=2)
    return add_outline(s.crop(s.getbbox()), OUT)


def sparkle(d, x, y, r, col=(255, 255, 255)):
    d.line((x - r, y, x + r, y), fill=col)
    d.line((x, y - r, x, y + r), fill=col)


def stripes_bg(w, h, c1, c2, step=10):
    img = Image.new("RGBA", (w, h), c1 + (255,))
    d = ImageDraw.Draw(img)
    for k in range(-h, w + h, step * 2):
        d.polygon([(k, 0), (k + step, 0), (k + step - h, h), (k - h, h)], fill=c2)
    return img


# ------------------------------------------------------------------ アイコン 800x800

def make_icon(name: str) -> Image.Image:
    B = 100
    img = stripes_bg(B, B, (255, 226, 160), (255, 214, 140), 6)
    d = ImageDraw.Draw(img)
    # 円形にくり抜かれる前提で、中央に寄せる
    d.ellipse((6, 6, 93, 93), fill=(255, 238, 200))
    d.ellipse((8, 8, 91, 91), outline=(255, 255, 240))
    m = mascot()
    img.alpha_composite(m, ((B - m.width) // 2, 14))
    for (x, y, r) in ((20, 22, 2), (80, 26, 2), (24, 70, 1), (78, 68, 1)):
        sparkle(d, x, y, r)
    return img.resize((800, 800), Image.NEAREST)


# ------------------------------------------------------------------ バナー 2560x1440

def make_banner(name: str, tagline: str) -> Image.Image:
    S = 6
    BW, BH = 2560 // S + 1, 1440 // S          # 427 x 240 のドット絵 → 6 倍
    k = BW / 320                               # 320x180 基準で決めた配置を伸ばす
    SW, SH = 1546 // S, 423 // S               # スマホでも必ず見える中央の範囲

    def P(x, y):
        return int(x * k), int(y * k)

    img = stripes_bg(BW, BH, (255, 226, 160), (255, 214, 140), 8)
    d = ImageDraw.Draw(img)
    shelf = int(132 * k)
    d.rectangle((0, shelf, BW, BH), fill=(196, 132, 84))
    d.rectangle((0, shelf, BW, shelf + 3), fill=(226, 166, 112))
    d.line((0, shelf + 4, BW, shelf + 4), fill=(150, 96, 60))
    rng = np.random.default_rng(1)
    for _ in range(80):
        x, y = rng.integers(0, BW), rng.integers(shelf + 8, BH)
        d.line((x, y, x + rng.integers(4, 16), y), fill=(176, 116, 74))
    for i, c in enumerate((PINK, YELLOW, MINT, SKY, PURPLE) * 8):
        x = i * 16
        d.rectangle((x, 0, x + 15, 9), fill=c)
        d.polygon([(x, 9), (x + 15, 9), (x + 7.5, 14)], fill=c)

    # 中央(スマホで見える範囲)にロゴと一言だけ
    sx0, sy0 = (BW - SW) // 2, (BH - SH) // 2
    logo = text_sprite(name, CREAM, scale=2)
    sub = text_sprite(tagline, (255, 255, 255), scale=1)
    gap = 4
    block_h = logo.height + gap + sub.height
    ly = sy0 + (SH - block_h) // 2
    lx = (BW - logo.width) // 2
    d.rounded_rectangle((lx - 5, ly - 3, lx + logo.width + 4, ly + logo.height + 2), 4, fill=PINK,
                        outline=OUT)
    img.alpha_composite(logo, (lx, ly))
    img.alpha_composite(sub, ((BW - sub.width) // 2, ly + logo.height + gap))

    # 左右(PC・テレビで見える): マスコットとジャンルの小物
    m = mascot()
    img.alpha_composite(m, (sx0 - m.width - 6, BH // 2 - m.height // 2 + 4))
    items = [("pan", 276, 76), ("quiz", 300, 98), ("pad", 280, 112), ("note", 304, 66),
             ("bulb", 266, 98), ("star", 12, 40), ("heart", 50, 44), ("clap", 30, 26),
             ("star", 296, 36), ("heart", 270, 44)]
    for kind, x, y in items:
        p = prop(kind)
        px, py = P(x, y)
        img.alpha_composite(p, (px - p.width // 2, py - p.height // 2))
    for (x, y) in ((90, 36), (230, 32), (120, 152), (200, 156), (160, 24)):
        sparkle(d, *P(x, y), 2)
    return img.resize((BW * S, BH * S), Image.NEAREST).crop((0, 0, 2560, 1440))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--name", default="ピコピコ堂")
    p.add_argument("--tagline", default="ドット絵でなんでも作る")
    p.add_argument("--out", default="branding/out")
    a = p.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    make_icon(a.name).convert("RGB").save(out / "icon_800.png")
    make_banner(a.name, a.tagline).convert("RGB").save(out / "banner_2560x1440.png")
    print(f"wrote {out}/icon_800.png, {out}/banner_2560x1440.png")


if __name__ == "__main__":
    main()
