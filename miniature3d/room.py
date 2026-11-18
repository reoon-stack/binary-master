"""ミニチュアの部屋(レシピ)。部品ごとに、形・置く場所・登場時刻・登場のしかたを決める。

座標: 床の上面が y=0。部屋は x, z とも -3〜3。左の壁は x=-3、奥の壁は z=-3。
anim: drop(上から落ちて弾む) / pop(ぽよんと出る) / rise(下から伸びる)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .mesh import box, cone, cylinder, sphere


def C(r, g, b):
    return (r / 255, g / 255, b / 255)


WOOD_D = C(138, 96, 70)
WOOD = C(196, 146, 102)
WOOD_L = C(222, 178, 132)
CREAM = C(240, 230, 212)
WHITE = C(246, 244, 238)
MUSTARD = C(232, 178, 74)
TEAL = C(96, 160, 156)
TEAL_L = C(140, 196, 186)
PINK = C(236, 150, 150)
GREEN = C(108, 168, 98)
GREEN_D = C(78, 136, 80)
TERRA = C(204, 116, 84)
ORANGE = C(236, 150, 80)
GRAY = C(90, 88, 96)


def rotate_x(parts, deg):
    """部品を x 軸まわりに回す(壁掛け時計などを縦にする)。"""
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    out = []
    for p in parts:
        arr = np.array(p, dtype="f4").reshape(-1, 10)
        for k in (0, 3):
            y, z = arr[:, k + 1].copy(), arr[:, k + 2].copy()
            arr[:, k + 1], arr[:, k + 2] = y * c - z * s, y * s + z * c
        out.append(arr.ravel().tolist())
    return out


@dataclass
class Item:
    key: str
    parts: list
    pos: tuple = (0.0, 0.0, 0.0)
    t: float = 0.0
    anim: str = "drop"
    sound: str = "tok"
    until: float = 99.0          # この時刻で消える(昼→夜の窓の差し替え用)
    spark: bool = True
    extra: dict = field(default_factory=dict)


def build_room() -> list[Item]:
    items: list[Item] = []
    add = items.append

    # 土台と床板
    add(Item("base", [box(6.8, 0.6, 6.8, WOOD_D, y=-0.6), box(6.9, 0.08, 6.9, C(120, 82, 60), y=-0.68)],
             t=0.25, anim="pop", sound="thud", spark=False))
    for i in range(6):
        col = WOOD if i % 2 == 0 else WOOD_L
        add(Item(f"plank{i}", [box(0.98, 0.08, 6.0, col)], pos=(-2.5 + i, 0, 0), t=1.3 + i * 0.28,
                 anim="drop", sound="plank"))

    # 壁と巾木
    add(Item("wall_l", [box(0.2, 3.6, 6.2, CREAM, x=-3.1, z=-0.1), box(0.06, 0.25, 6.0, WOOD_D, x=-2.98)],
             t=3.3, anim="rise", sound="whoosh", spark=False))
    add(Item("wall_b", [box(6.2, 3.6, 0.2, CREAM, z=-3.1, x=0.0), box(6.0, 0.25, 0.06, WOOD_D, z=-2.98)],
             t=3.7, anim="rise", sound="whoosh", spark=False))

    # 窓(昼のガラス → 夜のガラスに差し替え)
    frame = [box(1.7, 0.1, 0.1, WHITE, y=1.9), box(1.7, 0.1, 0.1, WHITE, y=3.2),
             box(0.1, 1.4, 0.1, WHITE, x=-0.8, y=1.9), box(0.1, 1.4, 0.1, WHITE, x=0.8, y=1.9),
             box(0.06, 1.3, 0.06, WHITE, y=1.95), box(1.6, 0.06, 0.06, WHITE, y=2.55)]
    add(Item("window", frame, pos=(1.25, 0, -2.95), t=4.6, anim="pop", sound="pop"))
    add(Item("glass_day", [box(1.6, 1.3, 0.04, C(170, 214, 240), y=1.95, glow=0.7)], pos=(1.25, 0, -2.99),
             t=4.6, anim="pop", sound="", spark=False, until=21.6))
    add(Item("glass_night", [box(1.6, 1.3, 0.04, C(70, 70, 140), y=1.95, glow=0.5)], pos=(1.25, 0, -2.99),
             t=21.6, anim="none", sound="", spark=False))
    add(Item("curtain", [box(0.3, 1.6, 0.08, PINK, x=-1.0, y=1.75), box(0.3, 1.6, 0.08, PINK, x=1.0, y=1.75),
                         box(2.4, 0.06, 0.06, WOOD_D, y=3.4)], pos=(1.25, 0, -2.88), t=5.2, anim="pop",
             sound="pop"))

    # ラグ
    add(Item("rug", [box(3.0, 0.04, 2.3, TEAL, y=0.08), box(2.6, 0.045, 1.9, TEAL_L, y=0.08),
                     box(2.2, 0.05, 1.5, TEAL, y=0.08)], pos=(0.5, 0, 0.7), t=6.0, anim="pop", sound="soft"))

    # ベッド(部品ごとに順番に)
    bx, bz = -1.85, -1.35
    add(Item("bed_base", [box(2.0, 0.45, 3.0, WOOD, y=0.08)] +
             [box(0.15, 0.3, 0.15, WOOD_D, x=x, z=z, y=0.0) for x in (-0.9, 0.9) for z in (-1.4, 1.4)],
             pos=(bx, 0, bz), t=7.0))
    add(Item("headboard", [box(2.1, 1.3, 0.16, WOOD_D, y=0.08), box(1.8, 0.9, 0.17, WOOD, y=0.35)],
             pos=(bx, 0, -2.93), t=7.4))
    add(Item("mattress", [box(1.9, 0.28, 2.9, WHITE, y=0.53)], pos=(bx, 0, bz), t=7.7, sound="soft"))
    add(Item("pillow", [box(1.2, 0.2, 0.55, C(250, 248, 244), y=0.81)], pos=(bx, 0, -2.4), t=8.0,
             sound="soft"))
    add(Item("blanket", [box(1.98, 0.12, 1.9, MUSTARD, y=0.8), box(1.99, 0.13, 0.2, C(250, 220, 150), y=0.8,
                                                                       z=-0.85)],
             pos=(bx, 0, bz + 0.45), t=8.3, sound="soft"))

    # 机と椅子
    dx, dz = 1.25, -2.35
    add(Item("desk", [box(2.2, 0.12, 1.0, WOOD_L, y=1.3)] +
             [box(0.1, 1.3, 0.1, WOOD_D, x=x, z=z) for x in (-1.0, 1.0) for z in (-0.4, 0.4)],
             pos=(dx, 0, dz), t=9.2))
    add(Item("chair", [box(0.8, 0.1, 0.8, MUSTARD, y=0.75), box(0.8, 0.9, 0.1, WOOD, y=0.85, z=0.36)] +
             [box(0.08, 0.75, 0.08, WOOD_D, x=x, z=z) for x in (-0.33, 0.33) for z in (-0.33, 0.33)],
             pos=(dx - 0.1, 0, -1.3), t=10.0))
    add(Item("laptop", [box(0.8, 0.05, 0.55, GRAY, y=1.42),
                        box(0.8, 0.55, 0.05, GRAY, y=1.45, z=-0.27),
                        box(0.7, 0.45, 0.02, C(150, 200, 255), y=1.5, z=-0.24, glow=1.0)],
             pos=(dx - 0.25, 0, dz + 0.05), t=10.8, sound="pop"))
    add(Item("lamp", [cylinder(0.18, 0.05, GRAY, y=1.42), cylinder(0.03, 0.55, GRAY, y=1.45),
                      cylinder(0.3, 0.3, C(255, 226, 170), y=1.95, r_top=0.14, glow=1.0)],
             pos=(dx + 0.75, 0, dz - 0.1), t=11.5, sound="pop"))
    add(Item("mug", [cylinder(0.1, 0.18, C(230, 110, 100), y=1.42, seg=10),
                     cylinder(0.085, 0.01, C(110, 70, 50), y=1.58, seg=10)],
             pos=(dx + 0.3, 0, dz + 0.3), t=12.1, sound="pop"))

    # 本棚と本(本は 1 冊ずつ)
    sx, sz = -2.65, 1.25
    shelf = [box(0.6, 2.6, 0.08, WOOD, z=-0.8), box(0.6, 2.6, 0.08, WOOD, z=0.8),
             box(0.6, 0.08, 1.68, WOOD, y=0.0), box(0.6, 0.08, 1.68, WOOD, y=0.85),
             box(0.6, 0.08, 1.68, WOOD, y=1.7), box(0.6, 0.08, 1.68, WOOD, y=2.55),
             box(0.04, 2.6, 1.68, WOOD_D, x=-0.28)]
    add(Item("shelf", shelf, pos=(sx, 0, sz), t=12.8))
    book_cols = [C(220, 90, 90), C(90, 140, 210), C(240, 200, 90), C(120, 180, 120), C(180, 120, 200),
                 C(240, 150, 100)]
    k = 0
    for level, y in enumerate((0.08, 0.93, 1.78)):
        z = -0.65
        n = 0
        while z < 0.6 and n < 6:
            h = 0.5 + 0.18 * ((k * 7) % 3) / 2
            w = 0.14 + 0.04 * (k % 2)
            add(Item(f"book{k}", [box(0.42, h, w, book_cols[k % len(book_cols)], y=y)],
                     pos=(sx + 0.02, 0, sz + z), t=13.4 + k * 0.12, anim="pop", sound="book", spark=False))
            z += w + 0.03
            k += 1
            n += 1

    # 観葉植物
    leaves = [cylinder(0.32, 0.55, TERRA, seg=10), cylinder(0.34, 0.08, C(180, 96, 70), y=0.5, seg=10),
              sphere(0.38, GREEN, y=0.95, seg=7, rings=4), sphere(0.3, GREEN_D, x=0.2, y=1.25, z=0.1, seg=7, rings=4),
              sphere(0.28, GREEN, x=-0.18, y=1.3, z=-0.1, seg=7, rings=4), cone(0.2, 0.5, GREEN_D, y=1.45)]
    add(Item("plant", leaves, pos=(2.55, 0.08, -0.9), t=16.0, anim="pop", sound="pop"))

    # 壁のポスターと時計
    poster = [box(0.05, 1.0, 1.3, WHITE, y=0.0), box(0.06, 0.8, 1.1, C(130, 190, 220), y=0.1),
              box(0.07, 0.35, 0.5, C(90, 150, 110), y=0.1, z=-0.2), box(0.07, 0.5, 0.45, C(110, 170, 120), y=0.1, z=0.2),
              box(0.075, 0.12, 0.12, C(250, 220, 120), y=0.65, z=0.35)]
    add(Item("poster", poster, pos=(-2.97, 1.9, -1.35), t=16.8, anim="pop", sound="pop"))
    clock = rotate_x([cylinder(0.3, 0.06, WHITE, seg=12), cylinder(0.25, 0.07, C(250, 250, 246), seg=12)], 90)
    clock += [box(0.03, 0.18, 0.02, GRAY, y=0.0, z=0.08), box(0.13, 0.03, 0.02, GRAY, x=0.06, y=0.0, z=0.08)]
    add(Item("clock", clock, pos=(-0.5, 2.7, -2.98), t=17.5, anim="pop", sound="pop"))

    # 床の小物
    add(Item("slippers", [box(0.22, 0.08, 0.45, PINK, x=-0.15), box(0.22, 0.08, 0.45, PINK, x=0.15)],
             pos=(-0.55, 0.08, 0.65), t=18.2, anim="pop", sound="pop"))
    add(Item("cushion", [box(0.7, 0.18, 0.7, ORANGE, y=0.08), box(0.6, 0.19, 0.6, C(246, 180, 110), y=0.08)],
             pos=(1.0, 0.0, 1.2), t=18.8, anim="drop", sound="soft"))

    # ねこ(最後にベッドへ飛び乗る)
    cat_col, cat_d = C(240, 160, 90), C(200, 120, 70)
    cat = [sphere(0.34, cat_col, y=0.25, sy=0.72, seg=8, rings=5),
           sphere(0.24, cat_col, x=0.0, y=0.52, z=0.3, seg=8, rings=5),
           cone(0.08, 0.16, cat_d, x=-0.12, y=0.68, z=0.3), cone(0.08, 0.16, cat_d, x=0.12, y=0.68, z=0.3),
           cylinder(0.05, 0.45, cat_d, x=0.0, y=0.12, z=-0.42, seg=6),
           box(0.05, 0.05, 0.02, C(40, 30, 30), x=-0.08, y=0.55, z=0.53),
           box(0.05, 0.05, 0.02, C(40, 30, 30), x=0.08, y=0.55, z=0.53)]
    add(Item("cat", cat, pos=(bx + 0.1, 0.92, bz + 0.6), t=19.6, anim="jump", sound="cat"))
    return items


# 部屋の大きさ(カメラの構図に使う)
ROOM_SPAN = 9.3
LAMP_POS = (1.25 + 0.75, 2.1, -2.35 - 0.1)
