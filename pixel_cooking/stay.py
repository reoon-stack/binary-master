"""ドット絵ショート「スワイプしないで！」第1話

  python -m pixel_cooking.stay out.mp4
  python -m pixel_cooking.stay out_dir --preview 1 5 11 16 20 25

画面の中に住むドットの住人が、見ている人の「スワイプ」に気づいて必死に引き止める。
跳ね返す → 芸で気を引く → バリケード → 買収 → 催眠 → 力尽きる。
最後にせり上がってくる「次の動画」は、この動画の最初の画面そのもの。そのまま冒頭に戻ってループする。

内部解像度 180x320 のドット絵を 6 倍(1080x1920)。音はチップチューン風に numpy で合成。
"""

from __future__ import annotations

import argparse
import math
import subprocess
import time
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from .gfx import FONT16, add_outline

VW, VH, S = 180, 320, 6
W, H = VW * S, VH * S
FPS = 30
DURATION = 27.0
SR = 44100
FLOOR_Y = 214            # 住人が立つ床の高さ(画面内座標)

OUT = (70, 44, 52)
BODY = (255, 206, 112)
BODY_SH = (236, 168, 84)
BODY_HI = (255, 236, 178)
PINK = (255, 140, 170)


def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def sm(p):
    p = clamp(p)
    return p * p * (3 - 2 * p)


def ease(t, a, b):
    return sm((t - a) / (b - a)) if b > a else float(t >= a)


def back(p, s=2.2):
    p = clamp(p) - 1
    return 1 + p * p * ((s + 1) * p + s)


# ------------------------------------------------------------------ 住人「ドット」

def critter(pose="idle", expr="normal", frame=0, face=1):
    """住人のスプライト(30x34)。足もと中央 = (15, 33)。face=1 で右向き。"""
    s = Image.new("RGBA", (30, 34))
    d = ImageDraw.Draw(s)
    bob = 1 if frame % 2 else 0
    by = 9 + (0 if pose in ("run", "push") else bob)
    # アンテナ(先にハート)
    sway = [-1, 0, 1, 0][frame % 4]
    d.line((15, by, 15 + sway, by - 6), fill=OUT)
    d.point((14 + sway, by - 8), fill=PINK)
    d.point((16 + sway, by - 8), fill=PINK)
    d.rectangle((14 + sway, by - 7, 16 + sway, by - 7), fill=PINK)
    d.point((15 + sway, by - 6), fill=PINK)
    # 足
    if pose == "run":
        fx = [(9, 13), (17, 21)] if frame % 2 else [(10, 14), (16, 20)]
        fy = [31, 29] if frame % 2 else [29, 31]
    else:
        fx, fy = [(9, 13), (17, 21)], [31, 31]
    for (x0, x1), y in zip(fx, fy):
        d.ellipse((x0, y - 2, x1, y + 2), fill=BODY_SH)
    # からだ
    d.ellipse((4, by, 26, by + 21), fill=BODY)
    d.ellipse((10, by + 9, 26, by + 21), fill=BODY_SH)
    d.ellipse((5, by + 1, 24, by + 18), fill=BODY)
    d.ellipse((8, by + 3, 13, by + 7), fill=BODY_HI)
    # うで
    arm = {"idle": [(3, by + 11), (25, by + 11)], "run": [(4, by + 9 + bob), (25, by + 13 - bob)],
           "up": [(2, by + 2), (26, by + 2)], "push": [(25, by + 8), (26, by + 13)],
           "cling": [(6, by - 2), (22, by - 2)], "juggle": [(2, by + 4 + 3 * (frame % 2)), (26, by + 7 - 3 * (frame % 2))],
           "cheer": [(1, by + 1), (27, by + 1)], "hold": [(6, by + 9), (22, by + 9)], "wave": [(3, by + 11), (27, by - 1 + 2 * (frame % 2))]}[pose]
    for ax, ay in arm:
        d.ellipse((ax - 2, ay - 2, ax + 2, ay + 2), fill=BODY_SH if ax > 15 else BODY)
    # 顔
    ex = 0 if pose != "push" else 2
    cx, cy = 15 + ex, by + 9
    if expr == "panic":
        for x in (cx - 4, cx + 4):
            d.ellipse((x - 2, cy - 3, x + 2, cy + 2), fill=(255, 255, 255), outline=OUT)
            d.point((x, cy), fill=OUT)
        d.ellipse((cx - 2, cy + 4, cx + 2, cy + 8), fill=(150, 60, 70))
        d.line((26, by + 2, 27, by + 5), fill=(120, 190, 255))
        d.point((27, by + 6), fill=(120, 190, 255))
    elif expr == "happy":
        for x in (cx - 4, cx + 4):
            d.line((x - 2, cy, x, cy - 2), fill=OUT)
            d.line((x, cy - 2, x + 2, cy), fill=OUT)
        d.arc((cx - 3, cy + 2, cx + 3, cy + 7), 0, 180, fill=OUT)
    elif expr == "cry":
        for x in (cx - 4, cx + 4):
            d.line((x - 2, cy - 1, x + 2, cy - 1), fill=OUT)
            d.line((x, cy, x, cy + 6 + frame % 3), fill=(120, 190, 255))
        d.arc((cx - 3, cy + 4, cx + 3, cy + 8), 200, 340, fill=OUT)
    elif expr == "sly":
        for x in (cx - 4, cx + 4):
            d.line((x - 2, cy, x + 2, cy), fill=OUT)
            d.point((x + 1, cy + 1), fill=OUT)
        d.arc((cx - 3, cy + 1, cx + 4, cy + 6), 0, 160, fill=OUT)
    elif expr == "dizzy":
        for x in (cx - 4, cx + 4):
            d.arc((x - 2, cy - 2, x + 2, cy + 2), 0, 300, fill=OUT)
        d.ellipse((cx - 1, cy + 4, cx + 1, cy + 6), fill=OUT)
    elif expr == "determined":
        for x, s_ in ((cx - 4, 1), (cx + 4, -1)):
            d.rectangle((x - 1, cy - 1, x + 1, cy + 2), fill=OUT)
            d.line((x - 2, cy - 3 - s_, x + 2, cy - 3 + s_), fill=OUT)
        d.line((cx - 2, cy + 5, cx + 2, cy + 5), fill=OUT)
    else:
        for x in (cx - 4, cx + 4):
            d.rectangle((x - 1, cy - 1, x + 1, cy + 2), fill=OUT)
            d.point((x, cy - 1), fill=(255, 255, 255))
        d.arc((cx - 2, cy + 3, cx + 2, cy + 6), 20, 160, fill=OUT)
    d.rectangle((cx - 8, cy + 3, cx - 6, cy + 4), fill=PINK)
    d.rectangle((cx + 6, cy + 3, cx + 8, cy + 4), fill=PINK)
    s = add_outline(s, OUT)
    if face < 0:
        s = s.transpose(Image.FLIP_LEFT_RIGHT)
    return s


def big_critter(*a, **k):
    """住人を 2 倍の大きさで(60x68)。足もと中央 = (30, 66)。"""
    spr = critter(*a, **k)
    return spr.resize((spr.width * 2, spr.height * 2), Image.NEAREST)


# ------------------------------------------------------------------ 小道具

def finger_sprite():
    """見ている人の指(下から伸びてくる)。"""
    s = Image.new("RGBA", (54, 120))
    d = ImageDraw.Draw(s)
    skin, sh, hi = (240, 196, 164), (214, 160, 128), (252, 222, 196)
    d.rounded_rectangle((8, 0, 46, 119), 18, fill=skin)
    d.rounded_rectangle((32, 6, 46, 119), 10, fill=sh)
    d.rounded_rectangle((14, 6, 40, 30), 9, fill=(250, 214, 200))
    d.rounded_rectangle((16, 8, 26, 16), 4, fill=(255, 238, 230))
    for y in (52, 56, 84, 88):
        d.line((16, y, 38, y), fill=sh)
    d.line((12, 20, 12, 110), fill=hi)
    return add_outline(s, (120, 70, 60))


def other_video_panel(seed):
    """よそのショート動画(せり上がってくる「次の動画」)。"""
    s = Image.new("RGBA", (VW, VH), (34, 36, 48, 255))
    d = ImageDraw.Draw(s)
    rng = np.random.default_rng(seed)
    top = tuple(int(c) for c in rng.integers(60, 140, 3))
    for y in range(VH):
        k = y / VH
        d.line((0, y, VW, y), fill=tuple(int(c * (1 - k) + 30 * k) for c in top))
    # ドットのねこ
    cx, cy = 90, 120
    d.polygon([(cx - 30, cy - 18), (cx - 22, cy - 40), (cx - 10, cy - 22)], fill=(250, 250, 250))
    d.polygon([(cx + 30, cy - 18), (cx + 22, cy - 40), (cx + 10, cy - 22)], fill=(250, 250, 250))
    d.ellipse((cx - 34, cy - 28, cx + 34, cy + 30), fill=(250, 250, 250))
    for x in (cx - 12, cx + 12):
        d.ellipse((x - 4, cy - 6, x + 4, cy + 4), fill=(40, 40, 50))
    d.polygon([(cx - 3, cy + 8), (cx + 3, cy + 8), (cx, cy + 12)], fill=(250, 150, 170))
    for i in range(3):
        d.rounded_rectangle((20, 200 + i * 16, 20 + 140 - i * 30, 208 + i * 16), 3, fill=(255, 255, 255, 150))
    return s


def crate():
    s = Image.new("RGBA", (16, 14))
    d = ImageDraw.Draw(s)
    d.rectangle((0, 0, 15, 13), fill=(200, 140, 80))
    d.rectangle((0, 0, 15, 2), fill=(226, 170, 110))
    d.line((1, 12, 14, 1), fill=(160, 104, 56))
    d.line((5, 0, 5, 13), fill=(176, 118, 66))
    d.line((10, 0, 10, 13), fill=(176, 118, 66))
    return add_outline(s, (100, 60, 36))


def heart_button():
    s = Image.new("RGBA", (34, 34))
    d = ImageDraw.Draw(s)
    d.ellipse((0, 0, 33, 33), fill=(255, 255, 255))
    d.ellipse((6, 9, 17, 20), fill=(240, 80, 110))
    d.ellipse((16, 9, 27, 20), fill=(240, 80, 110))
    d.polygon([(7, 17), (26, 17), (16.5, 27)], fill=(240, 80, 110))
    d.point((10, 12), fill=(255, 200, 210))
    return add_outline(s, OUT)


def sign(text, bg=(255, 236, 140)):
    w = int(ImageDraw.Draw(Image.new("L", (1, 1))).textlength(text, font=FONT16)) + 12
    s = Image.new("RGBA", (w, 34))
    d = ImageDraw.Draw(s)
    d.rectangle((w // 2 - 1, 18, w // 2 + 1, 33), fill=(150, 104, 66))
    d.rectangle((0, 0, w - 1, 19), fill=bg)
    d.fontmode = "1"
    d.text((6, 2), text, font=FONT16, fill=OUT)
    return add_outline(s, OUT)


def bubble(text):
    """吹き出し(ドットフォント)。しっぽは下中央。"""
    lines = text.split("\n")
    m = ImageDraw.Draw(Image.new("L", (1, 1)))
    w = max(int(m.textlength(ln, font=FONT16)) for ln in lines) + 14
    h = 18 * len(lines) + 10
    s = Image.new("RGBA", (w, h + 7))
    d = ImageDraw.Draw(s)
    d.rounded_rectangle((0, 0, w - 1, h - 1), 6, fill=(255, 255, 255))
    d.polygon([(w // 2 - 5, h - 2), (w // 2 + 5, h - 2), (w // 2, h + 5)], fill=(255, 255, 255))
    d.fontmode = "1"
    for i, ln in enumerate(lines):
        d.text((7, 5 + i * 18), ln, font=FONT16, fill=OUT)
    return add_outline(s, OUT)


# ------------------------------------------------------------------ 台本(時刻ごとの状態)

SWIPES = [  # (開始, 最大のずれ, 押し返し開始, 戻り終わり, 次の動画)
    (1.0, 92, 2.0, 2.9, "other"),
    (12.2, 18, 12.55, 12.9, "other"),
    (22.6, VH, 99, 99, "self"),
]

LINES = [  # (開始, 終了, 文字, 住人からの位置)
    (0.25, 1.1, "あっ！"),
    (1.1, 2.1, "待って！"),
    (2.9, 4.3, "まだ終わって\nないから！"),
    (4.5, 6.6, "見て見て！\nすごいでしょ？"),
    (7.1, 8.4, "ちょ、まだ…！"),
    (9.0, 11.6, "ここから先は\n通行止め！"),
    (13.0, 14.2, "よし！"),
    (14.6, 16.4, "これ押して\nくれたら…"),
    (16.5, 18.0, "…やっぱり\n帰らないで"),
    (18.6, 21.6, "あなたは だんだん\nこの動画を\n見たくなる…"),
    (23.6, 25.4, "また…\n来てね…"),
]


def scroll_offset(t):
    """画面のずれ(上にずれた量)と、そのとき下から見えている次の動画。"""
    for start, peak, ret0, ret1, kind in SWIPES:
        if kind == "self":
            if t >= start:
                return VH * sm((t - start) / (DURATION - start)) ** 1.0, kind
            continue
        if start <= t < ret1:
            up = peak * sm((t - start) / 0.6)
            if t >= ret0:
                q = (t - ret0) / (ret1 - ret0)
                up = peak * (1 - back(q, 1.6))
            return up, kind
    return 0.0, None


def critter_state(t):
    """(x, y, pose, expr, face)"""
    f = int(t * 8)
    x, y, pose, expr, face = 90, FLOOR_Y, "idle", "normal", 1
    if t < 0.25:
        pass
    elif t < 1.1:
        expr, pose = "panic", "up"
        y -= 6 * math.sin(clamp((t - 0.25) / 0.3) * math.pi)
    elif t < 2.0:                                          # 次の動画の上に飛び乗る
        pose, expr = "run", "determined"
        x = 90 + 10 * math.sin(t * 9)
    elif t < 2.9:                                          # どすん、どすんと踏みつけて押し返す
        pose, expr = "push", "determined"
        y = -abs(math.sin((t - 2.0) * 10)) * 14            # 次の動画のふちからの跳ね高さ
    elif t < 4.3:
        pose, expr = "cheer", "happy"
    elif t < 7.0:                                          # ジャグリング
        pose, expr = "juggle", "happy"
    elif t < 8.6:
        pose, expr = "up", "panic"
    elif t < 12.0:                                         # 箱を運んで積む
        k = (t - 9.0) / 3.0
        pose, expr = ("hold" if int(k * 6) % 2 == 0 else "run"), "determined"
        x = 60 + 60 * abs(math.sin(k * math.pi * 3))
        face = 1 if math.cos(k * math.pi * 3) > 0 else -1
    elif t < 13.0:
        pose, expr = "up", "panic"
    elif t < 14.4:
        pose, expr = "cheer", "happy"
        y -= 10 * abs(math.sin((t - 13.0) * 7))
    elif t < 16.5:
        pose, expr = "hold", "sly"
    elif t < 18.2:
        pose, expr = "idle", "panic"
    elif t < 22.0:                                         # 催眠
        pose, expr = "hold", "dizzy" if t > 21.2 else "sly"
    elif t < 22.6:
        pose, expr = "up", "panic"
    else:                                                  # 画面のふちにしがみつく → 手をふる
        if t < 23.6:
            pose, expr = "cling", "panic"
        else:
            pose, expr = "wave", "cry"
    return x, y, pose, expr, face, f


# ------------------------------------------------------------------ 描画

class Stay:
    def __init__(self):
        self.finger = finger_sprite()
        self.other = other_video_panel(4)
        self.crate = crate()
        self.heart = heart_button()
        self.sign_stop = sign("通行止め")
        self._bubbles = {}
        self.balls = [(255, 110, 110), (110, 190, 255), (140, 220, 120)]
        self.bg = self._background()
        self.first = None
        self.first = self.content(0.0)                    # 最後にせり上がってくる「この動画の最初」

    def _background(self):
        s = Image.new("RGB", (VW, VH))
        d = ImageDraw.Draw(s)
        for y in range(VH):
            k = y / VH
            c = tuple(int(a * (1 - k) + b * k) for a, b in zip((214, 210, 250), (255, 214, 200)))
            d.line((0, y, VW, y), fill=c)
        for y in range(4, VH, 10):
            for x in range(4 + (y // 10 % 2) * 5, VW, 10):
                d.point((x, y), fill=(255, 255, 255))
        # 床(タイル)
        for x in range(0, VW, 12):
            d.rectangle((x, FLOOR_Y + 1, x + 11, FLOOR_Y + 9), fill=(150, 200, 130) if (x // 12) % 2 else (130, 186, 112))
        d.rectangle((0, FLOOR_Y + 10, VW, FLOOR_Y + 30), fill=(170, 120, 90))
        for x in range(0, VW, 8):
            d.rectangle((x, FLOOR_Y + 14 + (x // 8 % 2) * 6, x + 5, FLOOR_Y + 16 + (x // 8 % 2) * 6), fill=(150, 104, 76))
        return s.convert("RGBA")

    def bub(self, text):
        if text not in self._bubbles:
            self._bubbles[text] = bubble(text)
        return self._bubbles[text]

    def content(self, t):
        """「この動画」の中身(スクロールでずれる部分)。"""
        img = self.bg.copy()
        d = ImageDraw.Draw(img)
        # 催眠のうずまき
        hyp = ease(t, 18.2, 18.7) * (1 - ease(t, 21.8, 22.3))
        if hyp > 0:
            ov = Image.new("RGBA", (VW, VH))
            od = ImageDraw.Draw(ov)
            cx, cy = 90, 120
            for k in range(24):
                a0 = k / 24 * 360 + t * 160
                od.pieslice((cx - 260, cy - 260, cx + 260, cy + 260), a0, a0 + 7.5,
                            fill=(160, 110, 230, int(120 * hyp)) if k % 2 else (255, 200, 240, int(90 * hyp)))
            img.alpha_composite(ov)
        x, y, pose, expr, face, f = critter_state(t)
        # 箱のバリケード(積み上がり → 最後に吹き飛ぶ)
        for i in range(8):
            ti = 9.4 + i * 0.32
            if t < ti:
                continue
            col, row = i % 4, i // 4
            cx = 34 + col * 34 + (row * 17)
            cy = FLOOR_Y - 13 - row * 14
            drop = (1 - back((t - ti) / 0.3, 1.5)) * -30
            fly = 0
            if t > 22.7:
                q = t - 22.7
                cx += (col - 1.5) * 60 * q
                cy += -120 * q + 160 * q * q
                fly = q
            if t > 12.2 and t < 13.0:
                cy += int(2 * math.sin(t * 60)) if t < 12.8 else 0
            img.alpha_composite(self.crate, (int(cx), int(cy + drop)))
            if fly > 1.5:
                break
        if 11.2 <= t < 22.8:
            sp = self.sign_stop
            sy = FLOOR_Y - 33 - 28 + int((1 - back((t - 11.2) / 0.35)) * -40)
            img.alpha_composite(sp, (VW - sp.width - 6, sy))
        # ジャグリングのボール
        if 4.6 <= t < 8.4:
            for i, col in enumerate(self.balls):
                ph = t * 3.2 + i * 2.1
                if t < 7.1:
                    bx = x + 28 * math.cos(ph)
                    by = y - 74 - 26 * abs(math.sin(ph))
                else:                                      # 落としてころころ
                    q = t - 7.1
                    bx = x + (i - 1) * 50 * q
                    by = min(FLOOR_Y - 6, y - 76 + 160 * q * q)
                d.ellipse((bx - 6, by - 6, bx + 6, by + 6), fill=col, outline=OUT)
                d.rectangle((bx - 3, by - 3, bx - 2, by - 2), fill=(255, 255, 255))
        # いいねボタン
        if 14.4 <= t < 18.2:
            s_ = back((t - 14.4) / 0.4)
            hb = self.heart.resize((max(1, int(34 * s_)), max(1, int(34 * s_))), Image.NEAREST)
            img.alpha_composite(hb, (int(x + 22), int(y - 70 - hb.height / 2)))
        # 催眠の振り子(コイン)
        if 18.4 <= t < 22.0:
            a = math.sin((t - 18.4) * 3.2) * 0.8
            px, py = x + 28, y - 58
            ex, ey = px + 38 * math.sin(a), py + 38 * math.cos(a)
            d.line((px, py, ex, ey), fill=OUT)
            d.ellipse((ex - 8, ey - 8, ex + 8, ey + 8), fill=(255, 214, 90), outline=OUT)
            d.rectangle((ex - 3, ey - 3, ex - 2, ey - 2), fill=(255, 250, 220))
        # 住人
        on_panel = 1.25 <= t < 2.9                        # 次の動画の上に乗っている間は frame() で描く
        if not (t >= 22.6 and self.first is not None) and not on_panel:
            spr = big_critter(pose, expr, f, face)
            img.alpha_composite(spr, (int(x - 30), int(y - 66)))
        # 「！」マーク
        if 0.2 <= t < 0.9 or 7.0 <= t < 7.6 or 12.15 <= t < 12.6 or 22.5 <= t < 22.9:
            d.rectangle((x + 22, y - 94, x + 25, y - 80), fill=(240, 70, 70))
            d.rectangle((x + 22, y - 77, x + 25, y - 74), fill=(240, 70, 70))
        # 吹き出し
        for a, b, text in LINES:
            if a <= t < b and t < 22.6 and not on_panel:
                bb = self.bub(text)
                pop = back((t - a) / 0.2)
                if pop < 0.99:
                    bb = bb.resize((max(1, int(bb.width * pop)), max(1, int(bb.height * pop))), Image.NEAREST)
                bx = int(clamp(x - bb.width / 2, 4, VW - bb.width - 4))
                img.alpha_composite(bb, (bx, int(y - 78 - bb.height)))
        return img

    def frame(self, t):
        o, kind = scroll_offset(t)
        o = max(0, int(round(o)))
        canvas = Image.new("RGBA", (VW, VH), (20, 20, 28, 255))
        canvas.alpha_composite(self.content(t), (0, -o))
        if o > 0:
            nxt = self.first if kind == "self" else self.other
            canvas.alpha_composite(nxt, (0, VH - o))
            d = ImageDraw.Draw(canvas)
            d.line((0, VH - o - 1, VW, VH - o - 1), fill=(10, 10, 14))
        # 次の動画の上に飛び乗って、踏みつけて押し返す
        if 1.25 <= t < 2.9:
            x, y, pose, expr, face, f = critter_state(t)
            edge = VH - max(o, 0)
            spr = big_critter(pose, expr, f, face)
            hop = y if t >= 2.0 else -abs(math.sin(t * 16)) * 4
            canvas.alpha_composite(spr, (int(x - 30), int(edge - 66 + hop)))
            for a, b, text in LINES:
                if a <= t < b:
                    bb = self.bub(text)
                    canvas.alpha_composite(bb, (int(clamp(x - bb.width / 2, 4, VW - bb.width - 4)), int(edge - 78 - bb.height)))
            if t > 2.0 and abs(math.sin((t - 2.0) * 10)) < 0.25:      # 踏みつけた瞬間の土ぼこり
                d2 = ImageDraw.Draw(canvas)
                for k in (-1, 1):
                    d2.ellipse((x + k * 24 - 4, edge - 6, x + k * 24 + 4, edge + 2), fill=(255, 255, 255))
        # 最後: 住人が画面のふちにしがみついて、手をふりながら上へ流れていく
        if t >= 22.6:
            x, y, pose, expr, face, f = critter_state(t)
            edge = VH - o
            cy = min(edge - 2, VH - 6)
            spr = big_critter(pose, expr, f, face)
            if t < 26.4:
                canvas.alpha_composite(spr, (int(x - 30), int(cy - 66)))
            for a, b, text in LINES:
                if a <= t < b and t >= 22.6:
                    bb = self.bub(text)
                    canvas.alpha_composite(bb, (int(x - bb.width / 2), int(cy - 78 - bb.height)))
        # 見ている人の指
        fy = None
        for start, peak, ret0, ret1, k2 in SWIPES:
            if start - 0.5 <= t < start + 0.8:
                p = (t - (start - 0.5)) / 1.3
                fy = VH - 70 * sm(p * 2.2) - (o if t > start else 0) * 0.9 + 140 * sm((p - 0.7) / 0.3)
        if 6.7 <= t < 8.4:                                  # そっと近づく指
            fy = VH - 40 * math.sin(clamp((t - 6.7) / 1.7) * math.pi)
        if 16.0 <= t < 17.6:                                # いいねボタンにのびる指(押さない)
            fy = VH - 60 * math.sin(clamp((t - 16.0) / 1.6) * math.pi)
        if fy is not None and fy < VH:
            canvas.alpha_composite(self.finger, (110, int(fy)))
        return canvas.convert("RGB").resize((W, H), Image.NEAREST)

    # ---- 音(チップチューン)
    def audio(self):
        n = int(SR * DURATION)
        mix = np.zeros(n, dtype=np.float32)

        def add(sig, t, g=1.0):
            i = int(t * SR)
            j = min(n, i + sig.size)
            if 0 <= i < n:
                mix[i:j] += sig[: j - i] * g

        def sq(f, dur, duty=0.5, dec=6.0):
            m = int(SR * dur)
            tt = np.arange(m) / SR
            w = np.where((tt * f) % 1 < duty, 1.0, -1.0)
            return (w * np.exp(-tt * dec) * np.minimum(1, tt / 0.004)).astype(np.float32)

        def tri(f, dur, dec=3.0):
            m = int(SR * dur)
            tt = np.arange(m) / SR
            w = 2 * np.abs(2 * ((tt * f) % 1) - 1) - 1
            return (w * np.exp(-tt * dec)).astype(np.float32)

        def sweep(f0, f1, dur, duty=0.5):
            m = int(SR * dur)
            f = np.linspace(f0, f1, m)
            ph = np.cumsum(f) / SR
            return (np.where(ph % 1 < duty, 1.0, -1.0) * np.linspace(1, 0.2, m)).astype(np.float32)

        # BGM: 明るい 8 ビット(BPM 150)。最後の 4.4 秒は止めて、悲しい音 → ループ前に元へ
        beat = 60 / 150
        mel = [72, 76, 79, 76, 74, 77, 81, 77, 72, 76, 79, 84, 83, 79, 74, 79]
        bass = [48, 48, 53, 53, 45, 45, 55, 55]
        hz = lambda m: 440 * 2 ** ((m - 69) / 12)
        t0, i = 0.0, 0
        while t0 < 22.4:
            hyp = 18.2 <= t0 < 22.0
            m = mel[i % len(mel)] - (5 if hyp else 0)
            add(sq(hz(m), beat * 0.9, 0.25, 5.0), t0, 0.07)
            if i % 2 == 0:
                add(tri(hz(bass[(i // 2) % len(bass)]), beat * 1.9, 1.5), t0, 0.16)
            if i % 2 == 1 and not hyp:
                k = int(SR * 0.04)
                add(np.random.default_rng(i).uniform(-1, 1, k).astype(np.float32) * np.exp(-np.arange(k) / (SR * 0.008)), t0, 0.06)
            t0 += beat / 2 if not hyp else beat
            i += 1
        # 効果音
        add(sweep(600, 1400, 0.12), 0.25, 0.12)                      # ！
        for start, peak, ret0, ret1, kind in SWIPES:
            add(sweep(300, 900, 0.35, 0.5) * 0.5, start, 0.1)        # スワイプ
            if kind == "other":
                add(sweep(200, 90, 0.18), ret0 + 0.05, 0.16)         # どすん
        for k in range(6):                                           # ジャグリング
            add(sq(1046.5 if k % 2 else 1318.5, 0.06, 0.5, 30), 4.6 + k * 0.42, 0.06)
        add(sweep(800, 200, 0.4), 7.1, 0.1)                          # 落とした
        for k in range(8):                                           # 箱をどん
            add(sq(110, 0.1, 0.5, 25), 9.4 + k * 0.32 + 0.25, 0.14)
        add(sq(1568, 0.25, 0.5, 8), 13.0, 0.06)                      # よし！
        add(sq(2093, 0.3, 0.5, 6), 14.5, 0.06)                       # いいねボタン
        m = int(SR * 3.4)
        tt = np.arange(m) / SR
        wob = np.sin(2 * np.pi * np.cumsum(420 + 120 * np.sin(2 * np.pi * 1.6 * tt)) / SR) * 0.4
        add((wob * np.minimum(1, tt / 0.5)).astype(np.float32), 18.4, 0.06)   # 催眠
        add(sweep(500, 2400, 0.9, 0.5) * 0.6, 22.6, 0.12)            # 吹き飛ぶ
        for k, mm in enumerate([67, 66, 65, 64]):                    # しょんぼり(ワワワワ〜)
            add(sq(hz(mm), 0.45 if k < 3 else 1.2, 0.5, 2.0), 23.6 + k * 0.45, 0.07)
        add(sq(hz(72), 0.3, 0.25, 5.0), DURATION - 0.3, 0.05)        # ループ前の 1 音
        mix /= max(1e-9, np.abs(mix).max()) / 0.9
        return mix


def make_video(out_path) -> Path:
    v = Stay()
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    wav = out.with_suffix(".wav")
    pcm = (np.clip(v.audio(), -1, 1) * 32767).astype(np.int16)
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", str(wav), "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p",
           "-tune", "animation", "-af", "loudnorm=I=-15:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "192k",
           "-ar", "44100", "-shortest", "-movflags", "+faststart", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for f in range(int(DURATION * FPS)):
        proc.stdin.write(v.frame(f / FPS).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg の書き出しに失敗しました")
    wav.unlink()
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("out", nargs="?", default="pixel_cooking/output/stay.mp4")
    p.add_argument("--preview", type=float, nargs="*")
    a = p.parse_args()
    if a.preview:
        v = Stay()
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        for t in a.preview:
            t0 = time.time()
            v.frame(t).save(out / f"stay_{t:05.2f}.png")
            print(f"{t:5.2f}s  {time.time() - t0:.3f}s")
        return
    print(make_video(a.out))


if __name__ == "__main__":
    main()
