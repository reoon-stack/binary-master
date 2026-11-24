"""失くし物の国 第1話「片方の靴下の行方」(3D ローポリ・ワンカット)

  python -m miniature3d.lostland out.mp4
  python -m miniature3d.lostland out_dir --preview 1 4 8 12 20 26 31

洗濯機の中で消えた片方の靴下を追いかけると、地下に「失くし物の国」があった。
靴下の家、傘の屋根、片耳イヤホンの街灯、自販機の下の小銭の泉。
最後に、靴下が小さな住人の「ふとん」になる。

カメラは切り替えず、洗濯機 → 縦穴 → 地下の国へひと続きで降りていく。
"""

from __future__ import annotations

import argparse
import math
import subprocess
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .mesh import box, cone, cylinder, sphere, to_array, transform
from .render import Renderer, rot_x, rot_y, rot_z, scale, translate
from .scene import FONT, band_noise, sfx, tone, write_wav

W, H, FPS = 1080, 1920, 30
DURATION = 33.0
SR = 44100


def C(r, g, b):
    return (r / 255, g / 255, b / 255)


def sm(p):
    p = min(1.0, max(0.0, p))
    return p * p * (3 - 2 * p)


def ease(t, a, b):
    return sm((t - a) / (b - a))


def lerp3(a, b, p):
    return tuple(a[i] + (b[i] - a[i]) * p for i in range(3))


# ------------------------------------------------------------------ 形

SOCK_MAIN = (C(236, 96, 96), C(250, 246, 236))           # 主役の靴下: 赤 + 白しま


def sock_parts(c1, c2, stripes=3, glow=0.0):
    """立った靴下(足首が上・つま先が +z)。原点 = かかとの下。"""
    p = [cylinder(0.32, 1.0, c1, y=0.25, seg=10, glow=glow),
         box(0.62, 0.5, 0.95, c1, y=0.0, z=0.42, glow=glow),
         sphere(0.31, c1, y=0.25, z=0.9, seg=10, rings=6, glow=glow),
         sphere(0.32, c1, y=0.28, z=-0.02, seg=10, rings=6, glow=glow),
         cylinder(0.335, 0.16, c2, y=1.12, seg=10, glow=glow)]
    for k in range(stripes):
        p.append(cylinder(0.33, 0.09, c2, y=0.42 + k * 0.2, seg=10, glow=glow))
    p.append(sphere(0.315, c2, y=0.25, z=0.93, seg=10, rings=6, sy=0.6, glow=glow))
    return p


def sock_house(c1, c2):
    p = transform(sock_parts(c1, c2, 3), scale(2.2, 2.2, 2.2))
    p += [box(0.4, 0.7, 0.05, C(90, 60, 50), y=0.0, z=2.95 * 0.75),
          box(0.36, 0.3, 0.05, C(255, 214, 130), x=0.0, y=1.7, z=0.72, glow=1.0),
          cylinder(0.06, 0.6, C(120, 100, 90), x=0.35, y=3.6, z=0.0, seg=6)]
    return p


def umbrella(col, h=2.2, r=1.35):
    p = [cylinder(0.05, h, C(70, 70, 80), seg=6),
         cone(r, 0.6, col, y=h - 0.05, seg=8),
         cone(r * 0.98, 0.58, tuple(v * 0.8 for v in col), y=h - 0.08, seg=8),
         sphere(0.07, C(70, 70, 80), y=h + 0.58, seg=6, rings=4)]
    for k in range(8):
        a = k / 8 * math.tau + math.pi / 8
        p.append(cylinder(0.02, 0.2, C(70, 70, 80), x=r * math.cos(a), y=h - 0.2, z=r * math.sin(a), seg=4))
    return p


def earbud_lamp():
    return [cylinder(0.06, 2.4, C(80, 80, 92), seg=6),
            cylinder(0.1, 0.55, C(246, 246, 250), y=2.15, seg=8),
            sphere(0.32, C(250, 250, 252), y=2.8, seg=10, rings=6),
            sphere(0.17, C(255, 220, 150), y=2.8, z=0.22, seg=8, rings=5, glow=1.0)]


def critter(col):
    """失くし物の国の住人(まるい小さな生き物)。原点 = 足もと。"""
    return [sphere(0.3, col, y=0.3, seg=10, rings=6, sy=0.92),
            sphere(0.08, C(255, 255, 255), x=-0.11, y=0.38, z=0.24, seg=6, rings=4),
            sphere(0.08, C(255, 255, 255), x=0.11, y=0.38, z=0.24, seg=6, rings=4),
            sphere(0.045, C(30, 26, 34), x=-0.11, y=0.38, z=0.31, seg=6, rings=4),
            sphere(0.045, C(30, 26, 34), x=0.11, y=0.38, z=0.31, seg=6, rings=4),
            sphere(0.05, C(255, 160, 170), x=-0.19, y=0.28, z=0.24, seg=5, rings=3),
            sphere(0.05, C(255, 160, 170), x=0.19, y=0.28, z=0.24, seg=5, rings=3),
            box(0.1, 0.06, 0.14, tuple(v * 0.75 for v in col), x=-0.12, y=0.0, z=0.05),
            box(0.1, 0.06, 0.14, tuple(v * 0.75 for v in col), x=0.12, y=0.0, z=0.05)]


SOCK_COLS = [(C(110, 160, 230), C(255, 255, 255)), (C(250, 200, 80), C(220, 120, 60)),
             (C(140, 200, 120), C(250, 250, 240)), (C(200, 140, 220), C(255, 230, 250)),
             (C(250, 150, 110), C(255, 240, 200)), (C(90, 90, 110), C(220, 220, 230)),
             (C(240, 120, 160), C(255, 255, 255)), (C(120, 210, 210), C(40, 90, 120))]
UMB_COLS = [C(240, 90, 90), C(90, 150, 230), C(250, 200, 70), C(120, 200, 120), C(200, 120, 220),
            C(250, 150, 90)]
CRIT_COLS = [C(255, 214, 120), C(160, 220, 250), C(250, 170, 190), C(180, 230, 160), C(220, 190, 250),
             C(255, 190, 140)]


# ------------------------------------------------------------------ 世界

WASHER_Y = 52.0
SHAFT_TOP, SHAFT_BOTTOM = 47.0, 14.0
RECEPTION = (0.0, 0.0, -6.2)
LAND = (0.0, 0.0, -4.6)
LAMPS = [(-7.5, -2.5), (-4.0, 4.2), (4.5, 4.5), (8.0, -1.0), (2.5, -3.5), (-2.8, -3.2), (6.0, 7.5),
         (-6.5, 7.0), (0.0, 9.0), (-9.5, 2.5), (9.8, 3.5)]


def build_world():
    static = []
    rng = np.random.default_rng(7)
    # --- 洗濯機(前面は「窓の穴が開いた枠」。奥に暗いドラムがあり、中の衣類が見える)
    wy = WASHER_Y
    white, panel = C(244, 244, 246), C(232, 233, 238)
    static += [box(4.2, 4.4, 2.6, white, y=wy - 2.2, z=-0.8),
               box(4.2, 0.75, 0.3, panel, y=wy + 1.45, z=1.25),
               box(4.2, 0.75, 0.3, panel, y=wy - 2.2, z=1.25),
               box(1.375, 2.9, 0.3, panel, x=-2.1375, y=wy - 1.45, z=1.25),
               box(1.375, 2.9, 0.3, panel, x=2.1375, y=wy - 1.45, z=1.25),
               box(0.8, 0.2, 0.05, C(120, 200, 240), x=1.2, y=wy + 1.8, z=1.42, glow=1.0),
               box(0.25, 0.25, 0.06, C(240, 90, 90), x=-1.4, y=wy + 1.8, z=1.42)]
    for i in range(28):
        a = i / 28 * math.tau
        static += transform([box(0.36, 0.28, 0.24, C(196, 200, 210))],
                            translate(1.33 * math.cos(a), wy + 1.33 * math.sin(a), 1.42) @ rot_z(a + math.pi / 2))
    static += transform([cylinder(1.45, 0.05, C(60, 64, 76), seg=28)], translate(0, wy, 0.55) @ rot_x(math.pi / 2))
    for i in range(10):
        a = i / 10 * math.tau
        static += transform([box(0.08, 0.5, 0.08, C(150, 154, 166))],
                            translate(0.95 * math.cos(a), wy + 0.95 * math.sin(a), 0.65) @ rot_z(a))
    static += transform([cylinder(0.34, 0.05, C(4, 4, 6), seg=16)], translate(0, wy, 0.6) @ rot_x(math.pi / 2))
    # --- 縦穴(輪っかと、壁のあかり)
    for k in range(28):
        y = SHAFT_TOP - k * 1.2
        ring = []
        for i in range(16):
            a = i / 16 * math.tau
            ring += transform([box(0.62, 0.22, 0.25, C(80, 70, 96))],
                              translate(1.55 * math.cos(a), y, 1.55 * math.sin(a)) @ rot_y(-a))
        static += ring
        if k % 2 == 0:
            a = k * 0.9
            static += [sphere(0.1, C(140, 220, 255), x=1.4 * math.cos(a), y=y + 0.5, z=1.4 * math.sin(a),
                              seg=6, rings=4, glow=1.0)]
    # --- 地面・道・広場
    static += [cylinder(18, 0.4, C(92, 74, 88), y=-0.4, seg=40),
               cylinder(3.0, 0.42, C(214, 180, 90), y=-0.4, seg=32)]              # 小銭の広場
    for k in range(90):                                                             # 小銭の石だたみ
        a, r = rng.uniform(0, math.tau), math.sqrt(rng.random()) * 2.9
        static += [cylinder(0.22, 0.05, C(230, 196, 110) if k % 3 else C(190, 190, 200), x=r * math.cos(a),
                            y=0.02, z=r * math.sin(a), seg=10)]
    for i in range(36):                                                             # 環状の小道
        a = i / 36 * math.tau
        static += transform([box(0.9, 0.03, 1.2, C(150, 128, 120))], translate(7 * math.cos(a), 0.0, 7 * math.sin(a))
                            @ rot_y(-a))
    # --- 靴下村
    houses = [(-9.0, -5.0, 0.6), (-10.5, 0.0, 1.2), (-8.5, 4.8, 2.0), (9.0, -5.5, -0.6), (10.5, -0.5, -1.4),
              (8.8, 5.0, -2.2), (-4.0, 10.0, 2.8), (4.2, 10.2, -2.9)]
    for i, (x, z, rot) in enumerate(houses):
        c1, c2 = SOCK_COLS[i % len(SOCK_COLS)]
        static += transform(sock_house(c1, c2), translate(x, 0, z) @ rot_y(rot))
    # --- 傘通り(屋台)
    for i, (x, z) in enumerate([(4.0, 2.0), (5.2, 0.2), (5.6, -2.0), (3.4, 3.8)]):
        col = UMB_COLS[i % len(UMB_COLS)]
        static += transform(umbrella(col), translate(x, 0, z))
        static += [box(1.2, 0.7, 0.8, C(170, 120, 80), x=x, y=0.0, z=z),
                   box(1.25, 0.06, 0.85, C(210, 160, 110), x=x, y=0.7, z=z)]
        for k in range(4):
            static += [sphere(0.12, UMB_COLS[(i + k + 2) % 6], x=x - 0.4 + k * 0.27, y=0.85, z=z, seg=6, rings=4)]
    for i in range(10):                                                             # 道ばたの忘れ傘
        a = rng.uniform(0, math.tau)
        r = rng.uniform(11, 15)
        static += transform(umbrella(UMB_COLS[i % 6], h=1.6, r=1.0), translate(r * math.cos(a), 0, r * math.sin(a))
                            @ rot_z(rng.uniform(-0.3, 0.3)))
    # --- イヤホン発電所(片耳イヤホンが光る塔)
    plant = (-5.0, 0.0, 1.2)
    static += [cylinder(1.3, 0.5, C(120, 120, 140), x=plant[0], z=plant[2], seg=16),
               cylinder(0.9, 2.4, C(150, 150, 170), x=plant[0], y=0.5, z=plant[2], seg=16, r_top=0.6)]
    for k in range(6):
        a = k / 6 * math.tau
        static += transform([cylinder(0.1, 0.6, C(246, 246, 250), seg=8), sphere(0.3, C(250, 250, 252), y=0.65, seg=10, rings=6),
                             sphere(0.14, C(150, 230, 255), y=0.65, z=0.2, seg=8, rings=5, glow=1.0)],
                            translate(plant[0] + 1.0 * math.cos(a), 1.2 + 0.5 * (k % 2), plant[2] + 1.0 * math.sin(a)) @ rot_y(-a))
    static += [sphere(0.5, C(160, 230, 255), x=plant[0], y=3.2, z=plant[2], seg=10, rings=6, glow=1.0)]
    # --- 街灯(片耳イヤホン)
    for (x, z) in LAMPS:
        static += transform(earbud_lamp(), translate(x, 0, z) @ rot_y(-math.atan2(-z, -x) + math.pi / 2))
    # --- 鍵の橋と小川
    static += [box(30, 0.05, 1.4, C(80, 130, 190), x=0, y=0.0, z=13.0, glow=0.3)]
    key = [box(3.0, 0.25, 0.45, C(230, 196, 90), y=0.3)]
    for i in range(14):
        a = i / 14 * math.tau
        key += [box(0.32, 0.25, 0.22, C(230, 196, 90), x=-2.1 + 0.75 * math.cos(a), y=0.3, z=0.75 * math.sin(a))]
    key += [box(0.25, 0.25, 0.5, C(230, 196, 90), x=1.2, y=0.3, z=0.4), box(0.25, 0.25, 0.35, C(230, 196, 90), x=0.7, y=0.3, z=0.35)]
    static += transform(key, translate(2.0, 0, 13.0) @ rot_y(math.pi / 2))
    # --- 靴下の受付(片方だけの靴下でできた壁)
    rx, _, rz = RECEPTION
    static += [box(9.0, 4.4, 0.6, C(120, 96, 110), x=rx, y=0.0, z=rz - 1.2),
               box(9.4, 0.4, 0.8, C(160, 130, 120), x=rx, y=4.4, z=rz - 1.2),
               box(2.4, 1.0, 0.8, C(200, 160, 120), x=rx + 2.6, y=0.0, z=rz),
               box(2.5, 0.08, 0.85, C(230, 200, 160), x=rx + 2.6, y=1.0, z=rz)]
    for row in range(5):
        for col in range(11):
            c1, c2 = SOCK_COLS[(row * 3 + col) % len(SOCK_COLS)]
            if (row, col) in ((1, 5),):
                continue                                                           # 1 か所だけ空き
            x = rx - 4.0 + col * 0.8
            y = 0.5 + row * 0.75
            static += transform(sock_parts(c1, c2, 2), translate(x, y, rz - 0.85) @ rot_y(math.pi) @ scale(0.36, 0.36, 0.36)
                                @ rot_x(-math.pi / 2 + 0.25 * ((row + col) % 3 - 1)))
    # --- 光る結晶(洞くつの天井から)
    for k in range(26):
        a, r = rng.uniform(0, math.tau), rng.uniform(6, 17)
        x, z = r * math.cos(a), r * math.sin(a)
        y = rng.uniform(11, 15)
        col = [C(150, 220, 255), C(220, 170, 255), C(255, 200, 150)][k % 3]
        static += [cone(0.25, -0.9, col, x=x, y=y, z=z, seg=5, glow=1.0)]
    return static


# ------------------------------------------------------------------ 動き

def keyframes(keys, t):
    """[(時刻, 値)] をなめらかにつなぐ(区間ごとに smoothstep)。"""
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t0 <= t <= t1:
            return lerp3(v0, v1, sm((t - t0) / (t1 - t0)))
    return keys[-1][1]


def sock_pos(t):
    """主役の靴下の位置と回転。"""
    wy = WASHER_Y
    if t < 1.3:                                          # 洗濯機の中でぐるぐる
        a = t * 5.5
        return (0.95 * math.cos(a), wy + 0.95 * math.sin(a), 0.95), t * 6, 0.42
    if t < 2.2:                                          # 中央の穴に吸い込まれる
        p = sm((t - 1.3) / 0.9)
        a = 1.3 * 5.5 + p * 7
        r = 0.95 * (1 - p)
        return (r * math.cos(a), wy + r * math.sin(a), 0.95 - 0.3 * p), t * 9, 0.42 * (1 - 0.6 * p)
    if t < 6.0:                                          # 縦穴を落ちる
        p = (t - 2.2) / 3.8
        y = SHAFT_TOP + 0.5 - (SHAFT_TOP + 0.5 - SHAFT_BOTTOM) * p ** 1.4
        return (0.25 * math.sin(t * 3), y, 0.25 * math.cos(t * 2.3)), t * 5, 0.55
    if t < 19.5:                                         # ひらひら舞い降りる
        p = (t - 6.0) / 13.5
        y = SHAFT_BOTTOM - (SHAFT_BOTTOM - 0.05) * (1 - (1 - p) ** 1.6)
        x = 3.2 * math.sin(p * 4.2) * (1 - p)
        z = LAND[2] * sm(p) + 2.0 * math.sin(p * 3) * (1 - p)
        return (x, y, z), math.sin(t * 2.4) * 0.7, 0.55
    return LAND, 0.0, 0.55


def sock_model(t):
    pos, ang, s = sock_pos(t)
    m = translate(*pos) @ rot_y(ang) @ scale(s, s, s)
    if t < 19.5:
        m = m @ rot_z(0.6 * math.sin(t * 3.1)) @ rot_x(0.5 * math.cos(t * 2.2))
        return m @ translate(0, -0.6, -0.45)
    if t < 19.9:
        k = math.sin((t - 19.5) / 0.4 * math.pi) * 0.25
        m = m @ scale(1 + k * 0.5, 1 - k, 1 + k * 0.5)
    m = m @ translate(0, 0.32, 0) @ rot_z(math.pi / 2) @ translate(0, -0.75, -0.4)   # 横に寝かせる(ふとん)
    if t > 25.4:                                          # 中に入った住人がもぞもぞ
        w = 0.05 * math.sin(t * 9) * math.exp(-max(0, t - 26.5) * 1.2)
        m = m @ scale(1 + w, 1 + w, 1)
    return m


class Critter:
    def __init__(self, i, rng):
        self.i = i
        self.col = CRIT_COLS[i % len(CRIT_COLS)]
        self.r = rng.uniform(4.0, 11.0)
        self.a0 = rng.uniform(0, math.tau)
        self.sp = rng.uniform(0.12, 0.25) * rng.choice([-1, 1])
        self.ph = rng.uniform(0, math.tau)

    def model(self, t):
        # 受付の前に集まる 3 匹
        if self.i < 3:
            home_a = self.a0 + self.sp * 18.6
            home = (self.r * math.cos(home_a), 0.0, self.r * math.sin(home_a))
            spot = [(-0.9, 0, LAND[2] + 0.7), (0.9, 0, LAND[2] + 0.8), (0.0, 0, LAND[2] + 1.3)][self.i]
            if t < 18.6:
                a = self.a0 + self.sp * t
                pos = (self.r * math.cos(a), 0.0, self.r * math.sin(a))
                face = a + (math.pi / 2 if self.sp > 0 else -math.pi / 2)
            else:
                p = ease(t, 18.6, 20.0 + 0.3 * self.i)
                pos = lerp3(home, spot, p)
                face = math.atan2(LAND[0] - pos[0], LAND[2] - pos[2])
                if self.i == 0 and t > 24.3:                      # 1 匹が靴下にもぐりこむ
                    q = ease(t, 24.3, 25.4)
                    pos = lerp3(spot, (LAND[0] + 0.1, 0.0, LAND[2] - 0.1), q)
                    s = 1 - 0.85 * q
                    hop = abs(math.sin(t * 9)) * 0.15 * (1 - q)
                    return translate(pos[0], pos[1] + hop, pos[2]) @ rot_y(face) @ scale(s, s, s)
            hop = abs(math.sin(t * 8 + self.ph)) * 0.18
            return translate(pos[0], hop, pos[2]) @ rot_y(face)
        a = self.a0 + self.sp * t
        pos = (self.r * math.cos(a), 0.0, self.r * math.sin(a))
        face = a + (math.pi / 2 if self.sp > 0 else -math.pi / 2)
        hop = abs(math.sin(t * 8 + self.ph)) * 0.18
        return translate(pos[0], hop, pos[2]) @ rot_y(face)


CAM_KEYS = [
    (0.0, ((0.6, WASHER_Y + 0.6, 11.5), (0, WASHER_Y - 0.1, 0))),
    (1.4, ((0, WASHER_Y, 5.6), (0, WASHER_Y, 0))),
    (2.25, ((0, WASHER_Y, 0.7), (0, WASHER_Y, -1))),
]
TOUR = [  # (時刻, 目, 注目点)
    (6.0, (0.3, SHAFT_BOTTOM + 2.5, 0.4), (0, SHAFT_BOTTOM - 4, 0)),
    (8.6, (15.0, 10.5, 19.0), (0.0, 1.5, 0.0)),
    (10.4, (-1.5, 6.2, 11.5), (-9.5, 1.5, 2.0)),         # 靴下村
    (12.6, (10.0, 5.0, 10.0), (4.6, 1.2, 1.0)),          # 傘通り
    (14.8, (1.2, 5.4, 8.0), (-5.0, 2.0, 1.2)),           # イヤホン発電所
    (16.8, (4.2, 4.4, 5.4), (0.0, 0.5, 0.0)),            # 小銭の泉
    (19.2, (2.4, 3.4, 0.8), (0.0, 0.4, LAND[2])),        # 受付へ
    (24.0, (1.2, 2.9, -1.2), (0.0, 0.3, LAND[2])),
    (26.8, (0.6, 2.6, -2.3), (0.0, 0.2, LAND[2])),       # ふとんのアップ
    (32.5, (14.0, 12.0, 17.0), (0.0, 1.0, -1.0)),        # 町の全景
]
LABELS = [(10.0, 12.2, "靴下村", "人口：世界中の「片方」"),
          (12.4, 14.5, "傘通り", "雨上がりに置き忘れた傘"),
          (14.6, 16.6, "イヤホン発電所", "片耳だけで光ります"),
          (16.7, 18.6, "小銭の泉", "自販機の下から湧いています")]


class LostLand:
    def __init__(self):
        rng = np.random.default_rng(11)
        self.r = Renderer(W, H)
        self.r.add_mesh("world", to_array(build_world()))
        self.r.add_mesh("sock", to_array(sock_parts(*SOCK_MAIN, 3)))
        self.crits = [Critter(i, rng) for i in range(12)]
        for i, c in enumerate(CRIT_COLS):
            self.r.add_mesh(f"crit{i}", to_array(critter(c)))
        # 洗濯機の中の衣類
        self.clothes = []
        for i in range(9):
            col = UMB_COLS[i % 6]
            key = f"cloth{i}"
            self.r.add_mesh(key, to_array([box(0.5, 0.12, 0.35, col), box(0.2, 0.13, 0.5, col, x=0.15)]))
            self.clothes.append((key, rng.uniform(0, math.tau), rng.uniform(0.3, 1.05)))
        self.r.add_mesh("coin", to_array([cylinder(0.11, 0.025, C(230, 196, 110), seg=10)]))
        self.coins = [dict(t0=rng.uniform(0, DURATION), vx=rng.normal(0, 0.45), vz=rng.normal(0, 0.45),
                           vy=rng.uniform(2.2, 3.0), sp=rng.uniform(5, 12)) for _ in range(24)]
        self.fonts = {k: ImageFont.truetype(FONT, s, index=0) for k, s in
                      (("hook", 92), ("title", 150), ("sub", 54), ("label", 64), ("label2", 42), ("mid", 66))}
        self._cache = {}

    def camera(self, t):
        fov = math.radians(42)
        if t < 2.25:
            eye, tg = keyframes([(k[0], k[1][0]) for k in CAM_KEYS], t), keyframes([(k[0], k[1][1]) for k in CAM_KEYS], t)
            return eye, tg, fov
        if t < 6.0:
            sp, _, _ = sock_pos(t)
            return (sp[0] + 0.35, sp[1] + 2.6, sp[2] + 0.45), (sp[0], sp[1] - 3.0, sp[2]), fov
        eyes = [(k[0], k[1]) for k in TOUR]
        tgs = [(k[0], k[2]) for k in TOUR]
        eye, tg = keyframes(eyes, t), keyframes(tgs, t)
        if t < 8.6:                                      # 縦穴を出た直後: 靴下を追いながら引いていく
            sp, _, _ = sock_pos(t)
            k = ease(t, 6.0, 8.6)
            tg = lerp3((sp[0], sp[1] - 2, sp[2]), tg, k)
        return eye, tg, fov

    def light(self, t, tg):
        lamps = [((x, 2.8, z), (0.9, 0.62, 0.32)) for (x, z) in LAMPS[:11]]
        lamps += [((-5.0, 3.2, 1.2), (0.3, 0.7, 1.0)), ((0.0, 1.0, 0.0), (0.9, 0.7, 0.3)),
                  ((LAND[0], 1.2, LAND[2] + 0.8), (0.9, 0.7, 0.45))]
        if t < 6.5:                                      # 洗濯機と縦穴は別の照明
            return dict(sun_dir=(0.3, 0.8, 1.0), sun_col=(0.62, 0.62, 0.66) if t < 2.3 else (0.25, 0.25, 0.35),
                        sky=(0.42, 0.43, 0.48) if t < 2.3 else (0.22, 0.2, 0.3), ground=(0.32, 0.3, 0.32) if t < 2.3 else (0.12, 0.1, 0.16),
                        lamps=[] if t < 2.3 else [((0, sock_pos(t)[0][1] - 1.5, 0), (0.5, 0.9, 1.2))],
                        glow=1.0, shadow_extent=8, center=tg, spec_default=0.15, shadow_floor=0.4)
        return dict(sun_dir=(-0.35, 1.0, 0.45), sun_col=(0.32, 0.3, 0.48), sky=(0.3, 0.27, 0.42),
                    ground=(0.16, 0.12, 0.18), lamps=lamps, glow=1.0, shadow_extent=16, center=(0, 0, 0),
                    falloff=0.45, spec_default=0.12, shadow_floor=0.35)

    def background(self, t):
        if t < 2.3:
            return ((0.86, 0.9, 0.96), (0.95, 0.93, 0.9))
        if t < 6.0:
            return ((0.03, 0.03, 0.06), (0.06, 0.05, 0.1))
        return ((0.06, 0.05, 0.14), (0.2, 0.12, 0.26), 0.6, t)

    def render_raw(self, t):
        draws = [("world", np.eye(4, dtype="f4")), ("sock", sock_model(t))]
        if t < 2.4:
            for key, a0, r in self.clothes:
                a = a0 + t * 5.5
                draws.append((key, translate(r * math.cos(a), WASHER_Y + r * math.sin(a), 0.95) @ rot_z(a * 2) @ rot_x(a)))
        for c in self.crits:
            draws.append((f"crit{c.i % len(CRIT_COLS)}", c.model(t)))
        for cn in self.coins:
            age = (t - cn["t0"]) % 1.2
            if t > 6:
                p = (cn["vx"] * age, 0.9 + cn["vy"] * age - 4.9 * age * age, cn["vz"] * age)
                if p[1] > 0.05:
                    draws.append(("coin", translate(*p) @ rot_x(age * cn["sp"])))
        eye, tg, fov = self.camera(t)
        raw = self.r.render(draws, eye, tg, fov, self.light(t, tg), self.background(t))
        return Image.frombytes("RGB", (W, H), raw).transpose(Image.FLIP_TOP_BOTTOM)

    # ---- 後処理: ブルーム・ビネット・場面のつなぎ
    def post(self, img, t):
        small = img.resize((W // 4, H // 4), Image.BILINEAR)
        a = np.asarray(small, dtype=np.float32) / 255
        bright = np.clip(a - 0.8, 0, 1) * 2.0
        bl = Image.fromarray((np.clip(bright, 0, 1) * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(8))
        out = np.asarray(img, dtype=np.float32) + np.asarray(bl.resize((W, H), Image.BILINEAR), dtype=np.float32) * 0.5
        yy, xx = np.mgrid[0:H:8, 0:W:8]
        v = 1 - 0.35 * np.clip(((xx - W / 2) / (W / 2)) ** 2 * 0.6 + ((yy - H / 2) / (H / 2)) ** 2 * 0.5, 0, 1)
        v = np.asarray(Image.fromarray((v * 255).astype(np.uint8)).resize((W, H), Image.BILINEAR), dtype=np.float32) / 255
        out *= v[..., None]
        # 洗濯機の穴に飛び込む瞬間だけ暗くする(カットではなく、穴の暗さでつなぐ)
        dark = ease(t, 1.95, 2.25) * (1 - ease(t, 2.25, 2.7))
        out *= 1 - dark
        return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))

    def text(self, key, lines, y, font, color=(255, 255, 255), stroke=0):
        if key in self._cache:
            return self._cache[key]
        im = Image.new("RGBA", (W, H))
        d = ImageDraw.Draw(im)
        yy = y
        for ln, f in lines:
            fo = self.fonts[f]
            d.text((W // 2, yy), ln, font=fo, fill=color + (255,), anchor="mm", stroke_width=stroke,
                   stroke_fill=(40, 20, 50, 255))
            yy += int(fo.size * 1.35)
        sh = Image.new("RGBA", (W, H), (20, 10, 30, 0))
        sh.putalpha(im.getchannel("A").point(lambda v: v * 150 // 255))
        sh = sh.filter(ImageFilter.GaussianBlur(12))
        out = Image.new("RGBA", (W, H))
        out.alpha_composite(sh, (0, 8))
        out.alpha_composite(im)
        self._cache[key] = out
        return out

    def label(self, title, sub):
        key = ("lab", title)
        if key not in self._cache:
            f1, f2 = self.fonts["label"], self.fonts["label2"]
            d0 = ImageDraw.Draw(Image.new("L", (1, 1)))
            w = int(max(d0.textlength(title, font=f1), d0.textlength(sub, font=f2))) + 90
            im = Image.new("RGBA", (w, 190))
            d = ImageDraw.Draw(im)
            d.rounded_rectangle((0, 0, w - 1, 189), 36, fill=(255, 250, 240, 230))
            d.text((w // 2, 66), title, font=f1, fill=(70, 50, 80), anchor="mm")
            d.text((w // 2, 140), sub, font=f2, fill=(130, 110, 140), anchor="mm")
            self._cache[key] = im
        return self._cache[key]

    def overlay(self, img, t):
        img = img.convert("RGBA")

        def put(lay, a, b, pos=(0, 0)):
            if a <= t < b:
                al = min(1.0, (t - a) / 0.35) * (1 - min(1.0, max(0.0, (t - (b - 0.4)) / 0.4)))
                l2 = lay.copy()
                l2.putalpha(l2.getchannel("A").point(lambda v: int(v * al)))
                img.alpha_composite(l2, pos)
        put(self.text("hook", [("片方の靴下、", "hook"), ("どこ行った？", "hook")], 260, "hook"), 0.15, 2.3)
        put(self.text("title", [("失くし物の国", "title"), ("なくしものの くに", "sub")], 330, "title", (255, 236, 170), 5),
            7.0, 9.8)
        for a, b, ti, su in LABELS:
            lay = self.label(ti, su)
            put(lay, a, b, ((W - lay.width) // 2, 1580))
        put(self.text("arrive", [("あなたの靴下は、", "mid"), ("ちゃんと届いていました", "mid")], 300, "mid"), 20.2, 24.2)
        put(self.text("punch", [("今日も誰かの", "mid"), ("ふとんになっています", "mid")], 300, "mid", (255, 230, 200)), 25.6, 29.0)
        put(self.text("zzz", [("z z z", "label")], 820, "label", (255, 255, 255)), 26.2, 29.0)
        put(self.text("end", [("あなたがなくしたものも、", "mid"), ("ここにあるかも。", "mid")], 280, "mid"), 29.0, DURATION + 1)
        put(self.text("ask", [("なくしたものをコメントで", "label2"), ("次回、探しに行きます", "label2")], 1620, "label2"),
            29.6, DURATION + 1)
        return img

    def render(self, t):
        return self.overlay(self.post(self.render_raw(t), t), t).convert("RGB")

    # ---- 音
    def audio(self):
        n = int(SR * DURATION)
        mix = np.zeros(n, dtype=np.float32)

        def add(sig, t, g=1.0):
            i = int(t * SR)
            j = min(n, i + sig.size)
            if 0 <= i < n:
                mix[i:j] += sig[: j - i] * g

        tt = np.arange(n) / SR
        # 洗濯機のゴウンゴウン(0〜2.2秒)
        wm = band_noise(int(SR * 2.4), 60, 500, 1) * (0.6 + 0.4 * np.sin(2 * np.pi * 1.8 * np.arange(int(SR * 2.4)) / SR))
        add(wm * np.minimum(1, np.linspace(3, 0, wm.size)), 0, 0.35)
        # 吸い込まれる音
        k = int(SR * 0.9)
        f = 200 + 1400 * (np.linspace(0, 1, k) ** 2)
        add((np.sin(2 * np.pi * np.cumsum(f) / SR) * np.linspace(0.2, 1, k) * 0.25).astype(np.float32) +
            band_noise(k, 800, 6000, 3) * np.linspace(0, 0.4, k), 1.4)
        # 落ちていく風
        k = int(SR * 4.2)
        wind = band_noise(k, 200, 2500, 4) * np.sin(np.linspace(0, np.pi, k)) ** 0.7
        add(wind, 2.2, 0.45)
        # 縦穴の輪っかを通過する「ヒュン」
        for j in range(10):
            add(sfx("whoosh", 20 + j)[: int(SR * 0.3)] * 0.5, 2.4 + j * 0.36, 0.5)
        # 不思議な国の音楽(6秒〜): オルゴール + やわらかいパッド
        notes = [523.3, 659.3, 784.0, 987.8, 880.0, 784.0, 659.3, 587.3, 659.3, 784.0, 880.0, 1046.5]
        chords = [[261.6, 329.6, 392.0, 493.9], [220.0, 277.2, 329.6, 440.0], [174.6, 220.0, 261.6, 349.2],
                  [196.0, 246.9, 293.7, 392.0]]
        t0 = 6.2
        step = 0.42
        i = 0
        while t0 < DURATION - 1:
            g = 0.22 if t0 < 24.5 else 0.14
            add(tone([notes[i % len(notes)]], 1.6, 3.0, (1.0, 0.25, 0.08, 0.05)), t0, g)
            if i % 8 == 0:
                add(tone(chords[(i // 8) % 4], step * 8.5, 0.7, (1.0, 0.2)), t0, 0.08)
            t0 += step if t0 < 24.5 else step * 1.5            # 最後は子守歌のようにゆっくり
            i += 1
        add(tone([523.3, 659.3, 784.0, 1046.5, 1318.5], 3.0, 1.3, (1.0, 0.25)), 7.0, 0.2)   # 国の全景
        # 小銭の泉のチャリン
        rng = np.random.default_rng(5)
        for _ in range(20):
            add(tone([rng.uniform(2600, 3600)], 0.25, 18, (1.0, 0.5)), rng.uniform(16.4, 19.0), 0.12)
        # 住人の「ぴゅ」
        for k2, tm in enumerate((11.0, 13.5, 18.9, 19.4, 20.1, 21.5, 23.0, 24.4)):
            m = int(SR * 0.16)
            fr = rng.uniform(900, 1400) * (1 + 0.6 * np.sin(np.linspace(0, np.pi, m)))
            add((np.sin(2 * np.pi * np.cumsum(fr) / SR) * np.sin(np.linspace(0, np.pi, m)) * 0.25).astype(np.float32), tm, 0.6)
        # 靴下の着地(ぽふっ)
        add(sfx("soft", 9), 19.5, 0.9)
        add(tone([1318.5, 1568.0], 1.2, 3.0, (1.0, 0.2)), 19.6, 0.12)
        # 洞くつの空気(6秒〜)
        add(band_noise(int(SR * (DURATION - 6)), 100, 1200, 8) * 0.04, 6.0)
        fade = int(SR * 1.5)
        mix[-fade:] *= np.linspace(1, 0, fade)
        mix /= max(1e-9, np.abs(mix).max()) / 0.9
        return mix


def make_video(out_path) -> Path:
    v = LostLand()
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    wav = out.with_suffix(".wav")
    write_wav(wav, v.audio())
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", str(wav), "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
           "-af", "loudnorm=I=-15:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
           "-shortest", "-movflags", "+faststart", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for f in range(int(DURATION * FPS)):
        proc.stdin.write(v.render(f / FPS).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg の書き出しに失敗しました")
    wav.unlink()
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("out", nargs="?", default="miniature3d/output/lostland.mp4")
    p.add_argument("--preview", type=float, nargs="*")
    a = p.parse_args()
    if a.preview:
        v = LostLand()
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        for t in a.preview:
            t0 = time.time()
            v.render(t).save(out / f"lost_{t:05.2f}.png")
            print(f"{t:5.2f}s  {time.time() - t0:.2f}s/frame")
        return
    print(make_video(a.out))


if __name__ == "__main__":
    main()
