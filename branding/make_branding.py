"""チャンネルのアイコン(800x800)とバナー(2560x1440)を作る。

どんなジャンルの動画にも合うよう、シンプルなフラットデザイン(グラデーション + 白いロゴ + 線のアイコン)。

  python branding/make_branding.py
  python branding/make_branding.py --name 別の名前 --tagline 別の一言

2 倍の大きさで描いてから縮小して、ふちをなめらかにしている。外部素材は使わない。
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
FONT_MED = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"

C1 = (255, 107, 107)   # コーラル
C2 = (255, 179, 71)    # オレンジ
INK = (60, 40, 50)
WHITE = (255, 255, 255)


def font(path, size):
    return ImageFont.truetype(path, size, index=0)   # index 0 = JP


def gradient(w, h, c1, c2, angle=35):
    a = math.radians(angle)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    t = (xx * math.cos(a) + yy * math.sin(a))
    t = (t - t.min()) / (t.max() - t.min())
    arr = np.array(c1) * (1 - t[..., None]) + np.array(c2) * t[..., None]
    return Image.fromarray(arr.astype(np.uint8)).convert("RGBA")


def soft_shadow(img, radius, offset=(0, 10), alpha=70):
    a = img.getchannel("A").point(lambda v: v * alpha // 255)
    sh = Image.new("RGBA", img.size, INK + (0,))
    sh.putalpha(a)
    sh = sh.filter(ImageFilter.GaussianBlur(radius))
    out = Image.new("RGBA", img.size)
    out.alpha_composite(sh, offset)
    out.alpha_composite(img)
    return out


def play_mark(size):
    """白い角丸の吹き出し + 再生ボタン + きらり。どんな動画にも合う記号。"""
    s = Image.new("RGBA", (size, size))
    d = ImageDraw.Draw(s)
    m = size * 0.1
    r = size * 0.2
    d.rounded_rectangle((m, m, size - m, size - m * 1.9), r, fill=WHITE)
    # 吹き出しのしっぽ
    d.polygon([(size * 0.3, size - m * 2.0), (size * 0.27, size - m * 0.9), (size * 0.45, size - m * 2.0)],
              fill=WHITE)
    # 再生ボタン(グラデーション)
    tri = Image.new("L", (size, size))
    cx, cy, k = size * 0.52, size * 0.45, size * 0.2
    ImageDraw.Draw(tri).polygon([(cx - k * 0.8, cy - k), (cx - k * 0.8, cy + k), (cx + k * 1.0, cy)],
                                fill=255)
    tri = tri.filter(ImageFilter.GaussianBlur(size * 0.004))
    s.paste(gradient(size, size, C1, C2), (0, 0), tri)
    # きらり
    sparkle(d, size * 0.84, size * 0.14, size * 0.07, C2)
    return s


def sparkle(d, x, y, r, color):
    pts = []
    for i in range(8):
        rr = r if i % 2 == 0 else r * 0.28
        a = -math.pi / 2 + i * math.pi / 4
        pts.append((x + rr * math.cos(a), y + rr * math.sin(a)))
    d.polygon(pts, fill=color)


def line_icon(kind, size, width, color):
    s = Image.new("RGBA", (size, size))
    d = ImageDraw.Draw(s)
    m = width
    if kind == "bulb":
        d.ellipse((size * 0.2, m, size * 0.8, size * 0.62), outline=color, width=width)
        d.line((size * 0.38, size * 0.75, size * 0.62, size * 0.75), fill=color, width=width)
        d.line((size * 0.42, size * 0.88, size * 0.58, size * 0.88), fill=color, width=width)
    elif kind == "note":
        d.ellipse((size * 0.12, size * 0.6, size * 0.42, size * 0.88), outline=color, width=width)
        d.line((size * 0.42, size * 0.74, size * 0.42, size * 0.12), fill=color, width=width)
        d.line((size * 0.42, size * 0.12, size * 0.8, size * 0.28), fill=color, width=width)
    elif kind == "heart":
        d.arc((m, size * 0.15, size * 0.52, size * 0.6), 150, 360, fill=color, width=width)
        d.arc((size * 0.48, size * 0.15, size - m, size * 0.6), 180, 30, fill=color, width=width)
        d.line((size * 0.08, size * 0.48, size * 0.5, size * 0.9), fill=color, width=width)
        d.line((size * 0.92, size * 0.48, size * 0.5, size * 0.9), fill=color, width=width)
    elif kind == "star":
        pts = []
        for i in range(10):
            r = size * 0.45 if i % 2 == 0 else size * 0.2
            a = -math.pi / 2 + i * math.pi / 5
            pts.append((size / 2 + r * math.cos(a), size / 2 + r * math.sin(a)))
        d.line(pts + [pts[0]], fill=color, width=width, joint="curve")
    elif kind == "chat":
        d.rounded_rectangle((m, size * 0.15, size - m, size * 0.7), size * 0.15, outline=color, width=width)
        d.line((size * 0.3, size * 0.7, size * 0.22, size * 0.9), fill=color, width=width)
        for x in (0.32, 0.5, 0.68):
            d.ellipse((size * x - width, size * 0.42 - width, size * x + width, size * 0.42 + width), fill=color)
    elif kind == "question":
        f = font(FONT_BOLD, int(size * 0.9))
        d.text((size / 2, size / 2), "?", font=f, fill=color, anchor="mm")
    elif kind == "camera":
        d.rounded_rectangle((m, size * 0.28, size - m, size * 0.85), size * 0.1, outline=color, width=width)
        d.ellipse((size * 0.32, size * 0.4, size * 0.68, size * 0.76), outline=color, width=width)
        d.line((size * 0.35, size * 0.28, size * 0.42, size * 0.14), fill=color, width=width)
        d.line((size * 0.42, size * 0.14, size * 0.6, size * 0.14), fill=color, width=width)
        d.line((size * 0.6, size * 0.14, size * 0.66, size * 0.28), fill=color, width=width)
    elif kind == "smile":
        d.ellipse((m, m, size - m, size - m), outline=color, width=width)
        d.arc((size * 0.28, size * 0.3, size * 0.72, size * 0.72), 20, 160, fill=color, width=width)
        for x in (0.36, 0.64):
            d.ellipse((size * x - width, size * 0.38 - width, size * x + width, size * 0.38 + width), fill=color)
    return s


# ------------------------------------------------------------------ アイコン

def make_icon() -> Image.Image:
    S = 1600
    img = gradient(S, S, C1, C2)
    d = ImageDraw.Draw(img)
    # 背景のやわらかい円
    for (x, y, r, a) in ((0.15, 0.2, 0.35, 40), (0.9, 0.85, 0.4, 35)):
        ov = Image.new("RGBA", (S, S))
        ImageDraw.Draw(ov).ellipse((S * (x - r), S * (y - r), S * (x + r), S * (y + r)), fill=WHITE + (a,))
        img.alpha_composite(ov)
    mark = soft_shadow(play_mark(int(S * 0.62)), 18, (0, 16), 60)
    img.alpha_composite(mark, ((S - mark.width) // 2, int(S * 0.2)))
    return img.resize((800, 800), Image.LANCZOS)


# ------------------------------------------------------------------ バナー

def make_banner(name: str, tagline: str) -> Image.Image:
    K = 2
    BW, BH = 2560 * K, 1440 * K
    SW, SH = 1546 * K, 423 * K
    img = gradient(BW, BH, C1, C2, angle=20)
    # 大きなやわらかい円
    for (x, y, r, a) in ((0.08, 0.3, 0.22, 34), (0.95, 0.75, 0.25, 30), (0.5, 1.05, 0.3, 20),
                         (0.7, 0.05, 0.12, 26)):
        ov = Image.new("RGBA", (BW, BH))
        R = BW * r
        ImageDraw.Draw(ov).ellipse((BW * x - R, BH * y - R, BW * x + R, BH * y + R), fill=WHITE + (a,))
        img.alpha_composite(ov)

    # 中央(スマホでも必ず見える範囲): ロゴと一言
    d = ImageDraw.Draw(img)
    cx, cy = BW // 2, BH // 2
    mark = play_mark(int(SH * 0.78))
    f_name = font(FONT_BOLD, int(SH * 0.42))
    f_tag = font(FONT_MED, int(SH * 0.15))
    name_w = d.textlength(name, font=f_name)
    total = mark.width + SH * 0.08 + name_w
    while total > SW * 0.96:
        f_name = font(FONT_BOLD, int(f_name.size * 0.95))
        name_w = d.textlength(name, font=f_name)
        total = mark.width + SH * 0.08 + name_w
    x0 = cx - total / 2
    logo = Image.new("RGBA", (BW, BH))
    ld = ImageDraw.Draw(logo)
    logo.alpha_composite(mark, (int(x0), int(cy - mark.height / 2 - SH * 0.02)))
    tx = x0 + mark.width + SH * 0.08
    ld.text((tx, cy - SH * 0.1), name, font=f_name, fill=WHITE, anchor="lm")
    ld.text((tx + 4, cy + SH * 0.27), tagline, font=f_tag, fill=WHITE, anchor="lm")
    img.alpha_composite(soft_shadow(logo, 14, (0, 10), 55))

    # 左右(PC・テレビで見える): いろいろなジャンルを表す線のアイコン
    icons = ["bulb", "note", "heart", "star", "chat", "question", "camera", "smile"]
    pos = [(0.07, 0.36), (0.13, 0.62), (0.05, 0.6), (0.17, 0.4), (0.93, 0.38), (0.87, 0.6),
           (0.95, 0.62), (0.83, 0.4)]
    for kind, (x, y) in zip(icons, pos):
        ic = line_icon(kind, int(BH * 0.09), int(BH * 0.008), WHITE + (200,))
        img.alpha_composite(ic, (int(BW * x - ic.width / 2), int(BH * y - ic.height / 2)))
    dd = ImageDraw.Draw(img)
    for (x, y, r) in ((0.23, 0.3, 0.012), (0.77, 0.68, 0.014), (0.3, 0.72, 0.008), (0.7, 0.3, 0.009)):
        sparkle(dd, BW * x, BH * y, BH * r * 1.6, WHITE)
    return img.resize((2560, 1440), Image.LANCZOS)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--name", default="ひまつぶしラボ")
    p.add_argument("--tagline", default="毎日、ちょっと気になる動画を。")
    p.add_argument("--out", default="branding/out")
    a = p.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    make_icon().convert("RGB").save(out / "icon_800.png")
    make_banner(a.name, a.tagline).convert("RGB").save(out / "banner_2560x1440.png")
    print(f"wrote {out}/icon_800.png, {out}/banner_2560x1440.png")


if __name__ == "__main__":
    main()
