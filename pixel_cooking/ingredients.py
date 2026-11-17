"""食材のドット絵と、刻んだ後のかけらの見た目。

Ing        : まな板で刻む食材(丸ごとの絵 + かけらの色・形)
GRAIN_KINDS: あとからボウルで加えるもの(ご飯・麺・豆腐・ルウなど)
EXTRAS     : 冒頭にちらっと見せる、刻まない材料の絵
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw

from .gfx import add_outline


@dataclass
class Ing:
    name: str
    sprite: Image.Image
    raw: tuple
    cooked: tuple
    size: int = 3          # かけらの大きさ
    shape: str = "cube"    # cube / strip / leaf / ring
    count: int = 30
    browned: tuple | None = None


def _canvas(w, h):
    s = Image.new("RGBA", (w, h))
    return s, ImageDraw.Draw(s)


# ------------------------------------------------------------------ 刻む食材

def onion():
    s, d = _canvas(36, 32)
    d.ellipse((0, 0, 35, 31), fill=(238, 228, 196))
    d.ellipse((2, 2, 33, 29), fill=(244, 236, 210))
    for k in (-10, -4, 3, 9):
        d.line((17 + k, 3, 17 + k, 28), fill=(224, 210, 168))
    d.ellipse((6, 5, 15, 11), fill=(252, 248, 232))
    d.rectangle((33, 13, 35, 18), fill=(190, 160, 100))
    return Ing("玉ねぎ", add_outline(s, (140, 118, 76)), (240, 236, 220), (216, 172, 96), 3, "cube", 34)


def chicken():
    s, d = _canvas(40, 28)
    d.ellipse((0, 4, 22, 27), fill=(234, 148, 140))
    d.ellipse((12, 0, 39, 24), fill=(236, 152, 144))
    d.ellipse((8, 6, 30, 26), fill=(238, 158, 150))
    for (x1, y1, x2, y2) in ((6, 10, 14, 14), (18, 6, 30, 9), (16, 18, 26, 22), (30, 14, 36, 16)):
        d.line((x1, y1, x2, y2), fill=(250, 226, 212), width=2)
    d.ellipse((14, 3, 22, 7), fill=(250, 196, 188))
    return Ing("鶏肉", add_outline(s, (150, 76, 70)), (236, 156, 146), (228, 196, 160), 4, "cube", 22,
               browned=(196, 140, 88))


def potato():
    s, d = _canvas(36, 28)
    d.ellipse((0, 0, 35, 27), fill=(214, 176, 112))
    d.ellipse((3, 2, 32, 24), fill=(226, 192, 128))
    for (x, y) in ((8, 8), (22, 6), (27, 17), (12, 19)):
        d.point((x, y), fill=(160, 120, 70))
        d.point((x + 1, y), fill=(180, 140, 86))
    d.ellipse((6, 4, 14, 9), fill=(240, 212, 156))
    return Ing("じゃがいも", add_outline(s, (120, 86, 46)), (246, 228, 170), (236, 204, 130), 5, "cube", 16,
               browned=(214, 170, 96))


def carrot():
    s, d = _canvas(44, 16)
    d.polygon([(0, 8), (34, 1), (36, 8), (34, 15)], fill=(236, 128, 44))
    d.line((4, 7, 32, 3), fill=(250, 170, 90))
    for x in (10, 18, 26):
        d.line((x, 5, x, 11), fill=(206, 104, 34))
    d.polygon([(35, 4), (43, 0), (40, 8), (43, 15), (35, 12)], fill=(80, 150, 60))
    return Ing("にんじん", add_outline(s, (130, 64, 24)), (240, 132, 48), (232, 116, 40), 4, "cube", 18)


def beef():
    s, d = _canvas(40, 26)
    d.rounded_rectangle((0, 0, 39, 25), 6, fill=(178, 52, 58))
    d.rounded_rectangle((3, 2, 36, 22), 5, fill=(196, 64, 70))
    for (x1, y1, x2, y2) in ((4, 6, 16, 9), (18, 14, 34, 11), (8, 18, 20, 20), (24, 4, 32, 6)):
        d.line((x1, y1, x2, y2), fill=(244, 214, 210))
    return Ing("牛肉", add_outline(s, (100, 26, 30)), (196, 66, 72), (120, 74, 56), 5, "strip", 20)


def pork():
    s, d = _canvas(40, 26)
    for i, y in enumerate((0, 8, 16)):
        d.rounded_rectangle((i * 2, y, 37 + i, y + 9), 4, fill=(236, 150, 150))
        d.line((i * 2 + 2, y + 2, 34 + i, y + 2), fill=(252, 236, 228), width=2)
        d.line((i * 2 + 3, y + 7, 33 + i, y + 7), fill=(212, 120, 124))
    return Ing("豚肉", add_outline(s, (140, 70, 72)), (238, 156, 156), (214, 176, 150), 5, "strip", 20,
               browned=(176, 120, 80))


def cabbage():
    s, d = _canvas(40, 34)
    d.pieslice((0, 0, 60, 60), 180, 270, fill=(150, 200, 96))
    d.pieslice((4, 4, 60, 60), 180, 270, fill=(196, 228, 140))
    for k in range(4):
        d.arc((6 + k * 5, 6 + k * 5, 56 - k * 2, 56 - k * 2), 185, 265, fill=(140, 190, 90))
    d.line((30, 30, 30, 4), fill=(230, 244, 200), width=2)
    return Ing("キャベツ", add_outline(s, (70, 110, 40)), (196, 228, 140), (176, 206, 110), 4, "leaf", 28)


def green_pepper():
    s, d = _canvas(30, 26)
    d.ellipse((0, 2, 29, 25), fill=(46, 140, 54))
    d.ellipse((3, 4, 26, 22), fill=(64, 168, 70))
    d.line((8, 6, 8, 20), fill=(40, 120, 46))
    d.line((18, 5, 18, 21), fill=(40, 120, 46))
    d.ellipse((5, 6, 10, 10), fill=(140, 220, 130))
    d.rectangle((12, 0, 16, 4), fill=(110, 150, 60))
    return Ing("ピーマン", add_outline(s, (24, 70, 30)), (70, 170, 70), (60, 150, 56), 3, "leaf", 24)


def sausage():
    s, d = _canvas(40, 22)
    for y in (0, 11):
        d.rounded_rectangle((0, y, 39, y + 10), 5, fill=(196, 96, 70))
        d.line((4, y + 2, 34, y + 2), fill=(232, 150, 120))
        d.line((4, y + 8, 34, y + 8), fill=(160, 70, 50))
    return Ing("ウインナー", add_outline(s, (100, 40, 26)), (206, 106, 80), (184, 84, 56), 4, "ring", 18)


def tomato():
    s, d = _canvas(34, 32)
    d.ellipse((0, 0, 33, 31), fill=(214, 46, 40))
    d.ellipse((3, 3, 30, 28), fill=(230, 64, 52))
    d.ellipse((7, 6, 14, 11), fill=(252, 150, 130))
    for a in range(0, 360, 72):
        x, y = 17 + 6 * math.cos(math.radians(a)), 15 + 6 * math.sin(math.radians(a))
        d.line((17, 15, x, y), fill=(60, 130, 50), width=2)
    return Ing("トマト", add_outline(s, (110, 20, 20)), (226, 60, 50), (206, 64, 44), 4, "cube", 24)


def daikon():
    s, d = _canvas(42, 22)
    d.rounded_rectangle((0, 0, 41, 21), 8, fill=(240, 240, 232))
    d.line((4, 4, 36, 4), fill=(255, 255, 250))
    for x in (10, 20, 30):
        d.line((x, 6, x + 2, 16), fill=(220, 220, 210))
    return Ing("大根", add_outline(s, (140, 140, 130)), (244, 244, 236), (230, 222, 196), 4, "cube", 22)


INGS = {f.__name__: f for f in (onion, chicken, potato, carrot, beef, pork, cabbage, green_pepper,
                                sausage, tomato, daikon)}


# ------------------------------------------------------------------ 冒頭に見せる材料(刻まない)

def egg_sprite():
    s, d = _canvas(14, 17)
    d.ellipse((0, 0, 13, 16), fill=(248, 238, 220))
    d.ellipse((7, 6, 13, 16), fill=(230, 214, 190))
    d.ellipse((1, 1, 11, 14), fill=(250, 242, 226))
    d.ellipse((3, 3, 6, 6), fill=(255, 252, 244))
    return add_outline(s, (150, 124, 96))


def roux_sprite():
    s, d = _canvas(26, 20)
    d.rounded_rectangle((0, 0, 25, 19), 2, fill=(120, 76, 36))
    for x in range(0, 26, 6):
        d.line((x, 0, x, 19), fill=(90, 54, 24))
    d.line((0, 10, 25, 10), fill=(90, 54, 24))
    d.line((1, 1, 24, 1), fill=(160, 110, 60))
    return add_outline(s, (60, 36, 16))


def noodles_sprite(color=(232, 200, 116)):
    s, d = _canvas(30, 24)
    d.ellipse((0, 0, 29, 23), fill=tuple(int(c * 0.85) for c in color))
    rng = np.random.default_rng(4)
    for _ in range(26):
        x, y = rng.integers(3, 24), rng.integers(3, 18)
        d.arc((x, y, x + 6, y + 5), rng.integers(0, 180), rng.integers(180, 360), fill=color)
    return add_outline(s, (120, 90, 40))


def spaghetti_sprite():
    s, d = _canvas(40, 12)
    for y in range(1, 11, 2):
        d.line((0, y, 39, y + (1 if y % 4 else 0)), fill=(236, 206, 130))
    d.line((0, 3, 39, 3), fill=(250, 226, 160))
    return add_outline(s, (140, 110, 50))


def tofu_sprite():
    s, d = _canvas(28, 22)
    d.rectangle((0, 0, 27, 21), fill=(246, 244, 236))
    d.line((0, 0, 27, 0), fill=(255, 255, 252))
    d.line((27, 0, 27, 21), fill=(220, 218, 206))
    d.line((0, 21, 27, 21), fill=(220, 218, 206))
    return add_outline(s, (150, 150, 140))


def miso_sprite():
    s, d = _canvas(26, 26)
    d.ellipse((0, 0, 25, 25), fill=(236, 236, 240))
    d.ellipse((3, 3, 22, 22), fill=(186, 136, 70))
    d.ellipse((7, 6, 13, 10), fill=(214, 168, 100))
    return add_outline(s, (110, 110, 120))


def rice_bag_sprite():
    s, d = _canvas(26, 22)
    d.ellipse((0, 0, 25, 21), fill=(240, 238, 230))
    rng = np.random.default_rng(2)
    for _ in range(30):
        d.point((rng.integers(3, 23), rng.integers(3, 19)), fill=(220, 216, 204))
    return add_outline(s, (150, 150, 140))


EXTRAS = {"egg": egg_sprite, "roux": roux_sprite, "noodles": noodles_sprite,
          "spaghetti": spaghetti_sprite, "tofu": tofu_sprite, "miso": miso_sprite,
          "rice": rice_bag_sprite}


# ------------------------------------------------------------------ ボウルで加えるもの

@dataclass
class GrainKind:
    name: str
    color: tuple
    style: str            # dot / strand / cube / block
    count: int
    bowl_color: tuple


GRAIN_KINDS = {
    "rice": GrainKind("ご飯", (246, 244, 234), "dot", 260, (246, 244, 236)),
    "noodles": GrainKind("麺", (236, 204, 124), "strand", 170, (230, 196, 112)),
    "spaghetti": GrainKind("スパゲッティ", (240, 214, 146), "strand", 170, (238, 210, 140)),
    "tofu": GrainKind("豆腐", (248, 246, 238), "cube", 16, (248, 246, 238)),
    "roux": GrainKind("カレールウ", (122, 76, 34), "block", 8, (122, 76, 34)),
    "carrot": GrainKind("にんじん", (240, 132, 48), "cube", 16, (240, 132, 48)),
    "beans": GrainKind("豆", (232, 214, 170), "dot2", 40, (232, 214, 170)),
    "miso": GrainKind("味噌", (186, 136, 70), "block", 4, (186, 136, 70)),
}
