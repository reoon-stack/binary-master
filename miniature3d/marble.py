"""ビー玉ピタゴラ装置(3D)。毎日、仕掛けの順番・色・木琴のメロディが変わる。

  python -m miniature3d.marble out.mp4 --seed 3
  python -m miniature3d.marble out_dir --preview 1 5 12 20 30 --seed 3

仕組み:
- 仕掛け(Module)を上から順に並べる。各仕掛けは「入口の位置と向き」から形とビー玉の通り道を作り、
  「出口の位置と向き」を次へ渡す
- ビー玉の動きは物理演算ではなく、ゆるやかな加速・放物線・らせんで「それらしく」描く(必ずゴールする)
- カメラはビー玉をなめらかに追いかけ、最初と最後は装置の全体を見せる
- 映像の後処理: 光のにじみ(ブルーム)、ミニチュア風のボケ、色味の調整
"""

from __future__ import annotations

import argparse
import math
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .mesh import _tri, box, cylinder, sphere, to_array, transform
from .render import Renderer, rot_axis, rot_y, rot_z, scale, translate
from .scene import FONT, band_noise, sfx, tone, write_wav

W, H, FPS = 1080, 1920, 30
SR = 44100
R = 0.16                 # ビー玉の半径
INTRO = 3.0              # 最初の全体ショット


def C(r, g, b):
    return (r / 255, g / 255, b / 255)


RAINBOW = [C(240, 90, 90), C(250, 160, 70), C(250, 214, 80), C(120, 200, 110), C(80, 180, 220),
           C(110, 130, 230), C(180, 120, 220), C(240, 130, 180)]

THEMES = [
    dict(name="wood", track=C(214, 168, 118), rail=C(160, 112, 74), wall=(C(236, 214, 182), C(226, 200, 166)),
         accent=C(230, 110, 90), bg=((0.98, 0.9, 0.8), (0.95, 0.78, 0.68))),
    dict(name="pastel", track=C(240, 236, 244), rail=C(180, 170, 220), wall=(C(226, 196, 160), C(214, 182, 146)),
         accent=C(250, 150, 170), bg=((0.86, 0.92, 1.0), (0.95, 0.84, 0.92))),
    dict(name="mint", track=C(236, 240, 230), rail=C(110, 180, 160), wall=(C(232, 206, 168), C(220, 192, 152)),
         accent=C(250, 190, 90), bg=((0.88, 0.98, 0.92), (0.98, 0.92, 0.82))),
]

MELODIES = {
    "ドレミ": [261.6, 293.7, 329.6, 349.2, 392.0, 440.0, 493.9, 523.3],
    "きらきら星": [261.6, 261.6, 392.0, 392.0, 440.0, 440.0, 392.0, 349.2],
    "かえるの合唱": [261.6, 293.7, 329.6, 349.2, 329.6, 293.7, 261.6, 261.6],
    "下りドレミ": [523.3, 493.9, 440.0, 392.0, 349.2, 329.6, 293.7, 261.6],
}


# ------------------------------------------------------------------ 形

def oriented_box(length, h, w, col, mid, ang_z=0.0, heading=0.0, glow=0.0):
    """長さ方向を x にした箱を、中心 mid に、z 軸まわり ang_z(傾き)・y 軸まわり heading で置く。"""
    parts = [box(length, h, w, col, y=-h / 2, glow=glow)]
    return transform(parts, translate(*mid) @ rot_y(heading) @ rot_z(ang_z))


def ramp(P, Q, theme, z=0.0, rails=True):
    """ビー玉の中心が P → Q を通るレール(板 + 両側の縁)。P, Q は (x, y)。"""
    dx, dy = Q[0] - P[0], Q[1] - P[1]
    L = math.hypot(dx, dy)
    a = math.atan2(dy, dx)
    nx, ny = -math.sin(a), math.cos(a)
    if nx * 0 + ny < 0:
        nx, ny = -nx, -ny
    mx, my = (P[0] + Q[0]) / 2 - nx * (R + 0.03), (P[1] + Q[1]) / 2 - ny * (R + 0.03)
    parts = oriented_box(L + 0.12, 0.06, 0.46, theme["track"], (mx, my + 0.03, z), a)
    if rails:
        for side in (-1, 1):
            parts += transform([box(L + 0.12, 0.12, 0.04, theme["rail"], y=0.0, z=side * 0.23)],
                               translate(mx, my, z) @ rot_z(a))
    return parts


def bracket(x, y, z_wall, z_front):
    d = z_front - z_wall
    return [box(0.1, 0.1, abs(d), C(150, 150, 160), x=x, y=y - 0.05, z=(z_wall + z_front) / 2)]


def funnel_parts(cx, cy, cz, r0, r1, depth, col, seg=28, bands=6):
    """内側が見えるじょうご(ふたなし・両面)。同心円のしま模様で、すり鉢の形がわかるようにする。"""
    out = []
    light = tuple(min(1.0, v * 1.18 + 0.06) for v in col)
    for b in range(bands):
        ra = r0 + (r1 - r0) * b / bands
        rb = r0 + (r1 - r0) * (b + 1) / bands
        ya, yb = cy + depth * b / bands, cy + depth * (b + 1) / bands
        bc = col if b % 2 == 0 else light
        for i in range(seg):
            a0, a1 = i / seg * math.tau, (i + 1) / seg * math.tau
            p0 = (cx + ra * math.cos(a0), ya, cz + ra * math.sin(a0))
            p1 = (cx + ra * math.cos(a1), ya, cz + ra * math.sin(a1))
            q0 = (cx + rb * math.cos(a0), yb, cz + rb * math.sin(a0))
            q1 = (cx + rb * math.cos(a1), yb, cz + rb * math.sin(a1))
            c4 = (*bc, 0.0)
            _tri(out, p0, q1, q0, c4)
            _tri(out, p0, p1, q1, c4)
            _tri(out, p0, q0, q1, c4)
            _tri(out, p0, q1, p1, c4)
    return out


def marble_parts(c1, c2):
    """2 色のしま模様のビー玉(転がっているのがわかるように)。"""
    out = []
    seg, rings = 16, 10

    def p(i, j):
        th, ph = j / rings * math.pi, i / seg * math.tau
        return (R * math.sin(th) * math.cos(ph), R * math.cos(th), R * math.sin(th) * math.sin(ph))

    for j in range(rings):
        for i in range(seg):
            col = (*(c2 if 3 <= j <= 6 and (i // 2) % 2 == 0 else c1), 0.0)
            a, b, c, d = p(i, j), p(i + 1, j), p(i + 1, j + 1), p(i, j + 1)
            for tri in ((a, b, c), (a, c, d)):
                t0, t1, t2 = tri
                n = np.cross(np.subtract(t1, t0), np.subtract(t2, t0))
                if np.dot(n, np.add(np.add(t0, t1), t2)) < 0:
                    t1, t2 = t2, t1
                if np.linalg.norm(n) > 1e-9:
                    _tri(out, t0, t1, t2, col)
    return out


# ------------------------------------------------------------------ 通り道

@dataclass
class Seg:
    t0: float
    t1: float
    fn: object            # u(0..1) → (x, y, z)
    ball: int
    roll: bool = True     # 転がっている(音が鳴る)か、空中か


def lin(P, Q, power=1.35):
    return lambda u: tuple(P[i] + (Q[i] - P[i]) * (u ** power) for i in range(3))


def hop(P, Q, h):
    return lambda u: (P[0] + (Q[0] - P[0]) * u, P[1] + (Q[1] - P[1]) * u + h * 4 * u * (1 - u),
                      P[2] + (Q[2] - P[2]) * u)


def fall(P, Q):
    """横に進みながら落ちる(放物線)。"""
    return lambda u: (P[0] + (Q[0] - P[0]) * u, P[1] + (Q[1] - P[1]) * u * u, P[2] + (Q[2] - P[2]) * u)


@dataclass
class Machine:
    theme: dict
    t: float = INTRO
    ball: int = 0
    statics: list = field(default_factory=list)
    dyn: list = field(default_factory=list)          # (key, parts, 時刻→行列)
    segs: list = field(default_factory=list)
    sounds: list = field(default_factory=list)       # (時刻, 種類, 値)
    ball_cols: list = field(default_factory=list)
    labels: list = field(default_factory=list)       # (時刻, 文字)
    goal_t: float = 0.0
    goal_pos: tuple = (0, 0, 0)
    cams: list = field(default_factory=list)         # (開始, 終了, カメラのずらし方)

    def seg(self, dur, fn, roll=True):
        self.segs.append(Seg(self.t, self.t + dur, fn, self.ball, roll))
        self.t += dur

    def new_ball(self, c1, c2):
        self.ball_cols.append((c1, c2))
        self.ball = len(self.ball_cols) - 1


# ------------------------------------------------------------------ 仕掛け
# どれも (m, E, d) を受け取る。E = ビー玉の入口位置 (x, y, z)、d = 進む向き(+1 右 / -1 左)。出口 (位置, 向き) を返す。

def m_start(m, E, d):
    th = m.theme
    m.statics += [box(1.0, 0.08, 0.5, th["track"], x=E[0] - 0.3 * d, y=E[1] - R - 0.08)]
    m.statics += bracket(E[0] - 0.3 * d, E[1] - R - 0.08, -0.9, -0.25)
    gx = E[0] + 0.3 * d
    t_open = m.t + 0.4

    def gate(t, gx=gx, y=E[1]):
        a = min(1.0, max(0.0, (t - t_open) / 0.3)) * 1.4
        return translate(gx, y - R, 0.25) @ rot_y(-a * d) @ translate(0, 0, -0.25)
    m.dyn.append(("gate", [box(0.06, 0.45, 0.5, th["accent"], y=0.0)], gate))
    m.sounds.append((t_open, "click", 0))
    m.seg(0.5, lambda u, E=E: E, roll=False)
    Q = (E[0] + 3.4 * d, E[1] - 1.2, 0.0)
    m.statics += ramp(E, Q, th)
    m.seg(1.7, lin(E, Q))
    m.labels.append((m.t - 2.2, "スタート！"))
    return Q, d


def m_zigzag(m, E, d):
    th = m.theme
    P = E
    dd = d
    for k in range(3):
        Q = (P[0] + 2.5 * dd, P[1] - 0.6, 0.0)
        m.statics += ramp(P, Q, th)
        m.statics += bracket(Q[0], Q[1] - R - 0.06, -0.9, -0.25)
        m.seg(0.75, lin(P, Q, 1.1))
        if k < 2:
            N = (Q[0] + 0.32 * dd, Q[1] - 0.62, 0.0)
            m.seg(0.28, fall(Q, N), roll=False)
            m.sounds.append((m.t, "clack", k))
            P = N
            dd = -dd
            P = (P[0], P[1], 0.0)
        else:
            P = Q
    return P, dd


def m_xylophone(m, E, d, melody):
    th = m.theme
    notes = MELODIES[melody]
    P = E
    bars = []
    for k in range(8):
        bx, by = E[0] + (0.55 + 0.46 * k) * d, E[1] - 0.34 * (k + 1)
        bars.append((bx, by))
        L = 0.62 - 0.03 * k
        col = RAINBOW[k]
        t_hit = m.t + 0.3 * (k + 1)

        def bar_m(t, bx=bx, by=by, t_hit=t_hit):
            w = 0.03 * math.exp(-max(0, t - t_hit) * 10) * math.sin(max(0, t - t_hit) * 60) * (t > t_hit)
            return translate(bx, by - R - 0.05 + w, 0)
        m.dyn.append((f"bar{k}", [box(0.3, 0.07, L, col, y=-0.035),
                                   box(0.04, 0.06, 0.04, C(220, 220, 225), x=-0.1, y=-0.09, z=L / 2 - 0.08),
                                   box(0.04, 0.06, 0.04, C(220, 220, 225), x=-0.1, y=-0.09, z=-L / 2 + 0.08)], bar_m))
        m.statics += [box(0.3, 0.04, 0.06, C(120, 110, 100), x=bx, y=by - R - 0.16, z=z) for z in (-0.22, 0.22)]
    m.statics += [box(0.06, 0.06, 0.6, C(120, 110, 100), x=E[0] + (0.55 + 0.46 * k) * d, y=E[1] - 0.34 * (k + 1) - R - 0.2)
                  for k in (0, 7)]
    m.labels.append((m.t, f"♪ {melody}"))
    m.cams.append((m.t, m.t + 3.0, (2.6, 1.2, 6.4)))
    for k, (bx, by) in enumerate(bars):
        Q = (bx, by, 0.0)
        m.seg(0.3, hop(P, Q, 0.28), roll=False)
        m.sounds.append((m.t, "note", notes[k]))
        P = Q
    Q = (P[0] + 0.5 * d, P[1] - 0.45, 0.0)
    m.seg(0.3, hop(P, Q, 0.2), roll=False)
    X = (Q[0] + 1.6 * d, Q[1] - 0.5, 0.0)
    m.statics += ramp(Q, X, th)
    m.sounds.append((m.t, "clack", 9))
    m.seg(0.6, lin(Q, X, 1.0))
    return X, d


def m_spiral(m, E, d):
    th = m.theme
    rc, turns, drop = 0.95, 2.0, 2.6
    Cc = (E[0], E[1], E[2] + rc)
    s = d
    n = int(36 * turns)
    for i in range(n):
        u0, u1 = i / n, (i + 1) / n
        a0, a1 = -math.pi / 2 + s * u0 * turns * math.tau, -math.pi / 2 + s * u1 * turns * math.tau
        p0 = (Cc[0] + rc * math.cos(a0), Cc[1] - drop * u0, Cc[2] + rc * math.sin(a0))
        p1 = (Cc[0] + rc * math.cos(a1), Cc[1] - drop * u1, Cc[2] + rc * math.sin(a1))
        mid = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2 - R - 0.03, (p0[2] + p1[2]) / 2)
        seglen = math.dist(p0, p1)
        heading = math.atan2(-(p1[2] - p0[2]), p1[0] - p0[0])
        slope = math.atan2(p1[1] - p0[1], math.hypot(p1[0] - p0[0], p1[2] - p0[2]))
        col = th["track"] if i % 2 == 0 else tuple(v * 0.93 for v in th["track"])
        m.statics += transform([box(seglen + 0.02, 0.05, 0.42, col, y=-0.025),
                                box(seglen + 0.02, 0.1, 0.04, th["rail"], y=0.0, z=0.21)],
                               translate(*mid) @ rot_y(heading) @ rot_z(slope))
    m.statics += [cylinder(0.08, drop + 1.2, C(200, 200, 210), x=Cc[0], y=Cc[1] - drop - 0.5, z=Cc[2], seg=10),
                  sphere(0.14, th["accent"], x=Cc[0], y=Cc[1] + 0.75, z=Cc[2], seg=10, rings=6)]

    def helix(u, Cc=Cc):
        uu = u ** 1.15
        a = -math.pi / 2 + s * uu * turns * math.tau
        return (Cc[0] + rc * math.cos(a), Cc[1] - drop * uu, Cc[2] + rc * math.sin(a))
    m.labels.append((m.t, "らせん"))
    m.cams.append((m.t, m.t + 3.0, (3.2, 1.4, 6.6)))
    m.sounds.append((m.t, "whirr", 3.0))
    m.seg(3.0, helix)
    P = helix(1.0)
    X = (P[0] + 1.4 * d, P[1] - 0.45, 0.0)
    m.statics += ramp((P[0], P[1]), (X[0], X[1]), th)
    m.seg(0.5, lin(P, X, 1.0))
    return X, d


def m_domino(m, E, d):
    th = m.theme
    A = (E[0] + 1.3 * d, E[1] - 0.55, 0.0)
    m.statics += ramp(E, A, th)
    m.seg(0.55, lin(E, A, 1.2))
    shelf_y = A[1] - R - 0.03
    n = 16
    span = 0.3 * n + 1.2
    m.statics += [box(span + 0.6, 0.06, 1.3, th["track"], x=A[0] + d * (span / 2 + 0.1), y=shelf_y - 0.06, z=0.2)]
    m.statics += bracket(A[0] + d * span * 0.5, shelf_y - 0.06, -0.9, -0.45)
    pos = []
    for k in range(n):
        x = A[0] + d * (0.55 + 0.3 * k)
        z = 0.2 + 0.32 * math.sin(k / (n - 1) * math.tau)
        pos.append((x, z))
    t_hit = m.t + 0.25
    m.seg(0.25, lin(A, (pos[0][0] - 0.12 * d, A[1], 0.0), 1.0))
    m.segs.append(Seg(m.t, m.t + 0.5, hop((pos[0][0] - 0.12 * d, A[1], 0.0), (pos[0][0] - 0.45 * d, A[1], 0.0), 0.05),
                      m.ball, False))
    for k, (x, z) in enumerate(pos):
        nxt = pos[min(k + 1, n - 1)]
        tx, tz = (nxt[0] - x, nxt[1] - z) if k < n - 1 else (x - pos[k - 1][0], z - pos[k - 1][1])
        heading = math.atan2(-tz, tx)
        t_fall = t_hit + 0.09 * k

        def dm(t, x=x, z=z, heading=heading, t_fall=t_fall, last=(k == n - 1)):
            a = min(1.0, max(0.0, (t - t_fall) / 0.2))
            ang = (1.32 if last else 1.18) * a * a
            return translate(x, shelf_y, z) @ rot_y(heading) @ translate(0.03, 0, 0) @ rot_z(-ang) @ translate(-0.03, 0, 0)
        m.dyn.append((f"dom{k}", [box(0.06, 0.44, 0.24, RAINBOW[k % len(RAINBOW)], y=0.0)], dm))
        m.sounds.append((t_fall + 0.18, "tick", k))
    m.labels.append((m.t, "ドミノ"))
    m.cams.append((t_hit - 0.6, m.t + 0.4, (1.2, 3.4, 6.0)))
    m.t = t_hit + 0.09 * (n - 1) + 0.2
    # 2 個目のビー玉にバトンタッチ
    c1, c2 = RAINBOW[(len(m.ball_cols) * 3) % len(RAINBOW)], C(255, 255, 255)
    m.new_ball(c1, c2)
    B0 = (pos[-1][0] + 0.32 * d, A[1], pos[-1][1])
    B1 = (A[0] + d * (span + 0.35), A[1], 0.2)
    m.segs.append(Seg(INTRO - 1, m.t, lambda u, B0=B0: B0, m.ball, False))
    m.sounds.append((m.t, "clack", 5))
    m.seg(0.6, lin(B0, B1, 1.0))
    X = (B1[0] + 1.5 * d, B1[1] - 0.55, 0.0)
    m.statics += ramp((B1[0], B1[1]), (X[0], X[1]), th)
    m.seg(0.5, lin(B1, X, 1.0))
    return X, d


def m_seesaw(m, E, d):
    th = m.theme
    piv = (E[0] + 1.9 * d, E[1] - 1.1, 0.0)
    L = 2.2
    up = 0.32

    t_land = m.t + 0.42

    def ang(t):
        if t < t_land:
            return up
        q = min(1.0, (t - t_land) / 0.14)
        return up - 2 * up * q + 0.05 * math.sin(max(0, t - t_land - 0.14) * 30) * math.exp(-max(0, t - t_land - 0.14) * 8)

    def board(t):
        return translate(*piv) @ rot_z(ang(t) * -d)
    m.dyn.append(("seesaw", [box(L, 0.08, 0.5, th["accent"], y=-0.04), box(0.08, 0.14, 0.5, th["rail"], x=-L / 2 + 0.04, y=0.0),
                             box(0.08, 0.14, 0.5, th["rail"], x=L / 2 - 0.04, y=0.0)], board))
    m.statics += [cylinder(0.1, 0.5, C(150, 150, 160), x=piv[0], y=piv[1] - 0.6, z=0.0, seg=8),
                  box(0.5, 0.06, 0.6, C(150, 150, 160), x=piv[0], y=piv[1] - 0.66)]

    def end_pos(t, side):
        a = ang(t) * -d
        x = side * (L / 2 - 0.25)
        return (piv[0] + x * math.cos(a), piv[1] + x * math.sin(a) + R + 0.0, 0.0)
    near = -d
    land = end_pos(t_land + 0.2, near)
    m.seg(0.42, fall(E, (land[0], end_pos(t_land, near)[1], 0.0)), roll=False)
    m.sounds.append((m.t, "thunk", 0))
    b_in = m.ball
    m.segs.append(Seg(m.t, m.t + 60, lambda u, t0=m.t: end_pos(t0 + 0.14 + u * 0.0, near), b_in, False))
    # 反対側のビー玉が飛ぶ
    c1, c2 = RAINBOW[(len(m.ball_cols) * 3 + 2) % len(RAINBOW)], C(255, 250, 230)
    m.new_ball(c1, c2)
    rest = end_pos(0, -near)
    m.segs.append(Seg(INTRO - 1, m.t + 0.1, lambda u, rest=rest: rest, m.ball, False))
    m.t += 0.1
    launch = end_pos(m.t, -near)
    Lnd = (piv[0] + d * 3.6, piv[1] - 0.2, 0.0)
    m.sounds.append((m.t, "whoosh", 0))
    m.labels.append((m.t - 0.5, "シーソー"))
    m.cams.append((m.t - 0.9, m.t + 0.9, (0.0, 1.8, 10.0)))
    m.seg(0.85, hop(launch, Lnd, 2.0), roll=False)
    m.sounds.append((m.t, "clack", 7))
    X = (Lnd[0] + 1.6 * d, Lnd[1] - 0.6, 0.0)
    m.statics += ramp((Lnd[0] - 0.3 * d, Lnd[1] + 0.1), (X[0], X[1]), th)
    m.seg(0.6, lin(Lnd, X, 1.0))
    return X, d


def m_funnel(m, E, d):
    th = m.theme
    r0, r1, depth = 0.22, 1.25, 0.7
    rim = (E[0] + 1.0 * d, E[1] - 0.35, 0.0)
    m.statics += ramp(E, rim, th)
    m.seg(0.45, lin(E, rim, 1.1))
    F = (rim[0], rim[1] - depth - 0.02, rim[2] + (r1 - 0.12))
    m.statics += [funnel_parts(F[0], F[1] - R, F[2], r0, r1, depth, th["accent"])]
    for i in range(28):                                 # ふちの輪(ふたにならないよう、小さな箱を並べる)
        a0 = i / 28 * math.tau
        m.statics += transform([box(0.3, 0.06, 0.07, th["rail"])],
                               translate(F[0] + (r1 + 0.02) * math.cos(a0), F[1] + depth - R, F[2] + (r1 + 0.02) * math.sin(a0))
                               @ rot_y(-a0 - math.pi / 2))
    m.statics += [cylinder(0.05, 1.2, C(150, 150, 160), x=F[0] - (r1 - 0.1), y=F[1] - 1.2, z=F[2], seg=6)]
    s = d
    dur = 3.2

    def swirl(u):
        rr = (r1 - 0.12) - (r1 - 0.12 - r0) * (u ** 1.6)
        a = -math.pi / 2 + s * (u ** 1.9) * 5.5 * math.tau
        y = F[1] + depth * (rr - r0) / (r1 - r0)
        return (F[0] + rr * math.cos(a), y, F[2] + rr * math.sin(a))
    m.labels.append((m.t, "ぐるぐる"))
    m.cams.append((m.t - 0.3, m.t + dur, (0.6, 4.2, 3.6)))
    m.sounds.append((m.t, "swirl", dur))
    m.seg(dur, swirl)
    P = swirl(1.0)
    Bm = (F[0], F[1] - 1.1, 0.0)
    m.seg(0.35, fall(P, Bm), roll=False)
    m.sounds.append((m.t, "clack", 11))
    X = (Bm[0] + 1.6 * d, Bm[1] - 0.5, 0.0)
    m.statics += ramp((Bm[0] - 0.2 * d, Bm[1] + 0.08), (X[0], X[1]), th)
    m.seg(0.55, lin(Bm, X, 1.0))
    return X, d


def m_loop(m, E, d):
    th = m.theme
    A = (E[0] + 1.8 * d, E[1] - 1.3, 0.0)
    m.statics += ramp(E, A, th)
    m.seg(0.45, lin(E, A, 1.6))
    rl = 0.75
    Cc = (A[0], A[1] + rl, 0.0)
    n = 40
    for i in range(n):
        a0, a1 = i / n * math.tau, (i + 1) / n * math.tau
        zz = -0.18 + 0.36 * (i + 0.5) / n
        p0 = (Cc[0] + d * rl * math.sin(a0), Cc[1] - rl * math.cos(a0))
        p1 = (Cc[0] + d * rl * math.sin(a1), Cc[1] - rl * math.cos(a1))
        am = (a0 + a1) / 2
        out = (d * math.sin(am), -math.cos(am))
        mid = ((p0[0] + p1[0]) / 2 + out[0] * (R + 0.03), (p0[1] + p1[1]) / 2 + out[1] * (R + 0.03) + 0.025, zz)
        seglen = math.dist(p0, p1)
        m.statics += oriented_box(seglen + 0.02, 0.05, 0.42, th["track"] if i % 2 else th["rail"], mid,
                                  math.atan2(p1[1] - p0[1], p1[0] - p0[0]))

    def loop(u):
        a = u * math.tau
        return (Cc[0] + d * rl * math.sin(a), Cc[1] - rl * math.cos(a), -0.18 + 0.36 * u)
    m.labels.append((m.t, "1回転！"))
    m.sounds.append((m.t, "whoosh", 1))
    m.seg(0.85, loop)
    P = loop(1.0)
    X = (P[0] + 1.9 * d, P[1] - 0.35, 0.18)
    m.statics += ramp((P[0], P[1]), (X[0], X[1]), th, z=0.18)
    m.seg(0.6, lin(P, X, 0.8))
    return (X[0], X[1], 0.0), d


def m_goal(m, E, d):
    th = m.theme
    G = (E[0] + 1.8 * d, E[1] - 0.55, 0.0)
    rim = (G[0] - 0.05 * d, G[1], 0.0)
    m.statics += ramp(E, (rim[0] - 0.25 * d, rim[1]), th)
    m.seg(0.7, lin(E, rim, 1.1))
    cup_y = G[1] - 0.75
    m.statics += [cylinder(0.36, 0.55, th["accent"], x=G[0] + 0.3 * d, y=cup_y, z=0.0, seg=22),
                  cylinder(0.3, 0.02, C(60, 40, 40), x=G[0] + 0.3 * d, y=cup_y + 0.54, z=0.0, seg=22),
                  cylinder(0.42, 0.06, C(250, 214, 80), x=G[0] + 0.3 * d, y=cup_y + 0.52, z=0.0, seg=22, r_top=0.4)]
    m.statics += bracket(G[0] + 0.3 * d, cup_y, -0.9, -0.35)
    inside = (G[0] + 0.3 * d, cup_y + 0.3, 0.0)
    m.seg(0.35, fall(rim, inside), roll=False)
    m.goal_t = m.t
    m.goal_pos = inside
    m.sounds.append((m.t, "bell", 0))
    # 旗が上がる
    fx = G[0] + 0.3 * d + 0.7 * d

    def flag(t, t0=m.t):
        q = min(1.0, max(0.0, (t - t0 - 0.15) / 0.6))
        q = 1 - (1 - q) ** 3
        return translate(fx, cup_y + 0.3 + 1.0 * q, 0.0)
    m.statics += [cylinder(0.03, 1.8, C(200, 200, 210), x=fx, y=cup_y, z=0.0, seg=6)]
    m.dyn.append(("flag", [box(0.04, 0.4, 0.6, C(240, 80, 80), y=0.0, z=0.3),
                           box(0.045, 0.12, 0.2, C(255, 255, 255), y=0.14, z=0.3)], flag))
    m.seg(6.0, lambda u, p=inside: p, roll=False)
    return inside, d


MODULES = {"zigzag": m_zigzag, "xylophone": m_xylophone, "spiral": m_spiral, "domino": m_domino,
           "seesaw": m_seesaw, "funnel": m_funnel, "loop": m_loop}


def build_machine(seed: int):
    rng = np.random.default_rng(seed)
    theme = THEMES[seed % len(THEMES)]
    melody = list(MELODIES)[seed % len(MELODIES)]
    order = list(MODULES)
    rng.shuffle(order)
    # 木琴とドミノは毎回入れる(音と見た目の山場)。そのほかから 4 つ
    core = [k for k in order if k in ("xylophone", "domino")]
    rest = [k for k in order if k not in core][:4]
    seq = [k for k in order if k in core + rest]
    m = Machine(theme)
    c1 = RAINBOW[seed % len(RAINBOW)]
    m.new_ball(c1, C(255, 255, 255))
    E, d = (-1.7, 0.0, 0.0), 1
    E, d = m_start(m, E, d)
    for k in seq:
        # 画面の外へはみ出さないよう、端に寄ったら向きを変える
        if E[0] > 1.2:
            d = -1
        elif E[0] < -1.2:
            d = 1
        if k == "xylophone":
            E, d = m_xylophone(m, E, d, melody)
        else:
            E, d = MODULES[k](m, E, d)
        E = (E[0], E[1], 0.0)
    m_goal(m, E, d)
    m.seq = seq
    m.melody = melody
    return m


# ------------------------------------------------------------------ 映像

class MarbleVideo:
    def __init__(self, seed=0):
        self.m = build_machine(seed)
        self.duration = self.m.goal_t + 5.5
        m = self.m
        # 背景の壁と床
        ys = [p for seg in m.segs for p in (seg.fn(0)[1], seg.fn(1)[1])]
        self.top, self.bottom = max(ys) + 1.2, min(ys) - 1.6
        xs = [p for seg in m.segs for p in (seg.fn(0)[0], seg.fn(1)[0])]
        self.cx = (max(xs) + min(xs)) / 2
        self.width = max(xs) - min(xs) + 2.6
        wall = []
        rng = np.random.default_rng(seed + 3)
        hh = self.top - self.bottom + 3
        for i in range(-7, 8):
            col = m.theme["wall"][i % 2]
            wall += [box(1.2, hh, 0.1, col, x=self.cx + i * 1.2, y=self.bottom - 1, z=-0.95)]
            wall += [box(0.02, hh, 0.11, tuple(v * 0.8 for v in col), x=self.cx + i * 1.2 + 0.6, y=self.bottom - 1, z=-0.95)]
            for _ in range(6):
                gy = rng.uniform(self.bottom, self.top)
                wall += [box(rng.uniform(0.2, 0.6), 0.015, 0.105, tuple(v * 0.9 for v in col),
                             x=self.cx + i * 1.2 + rng.uniform(-0.3, 0.3), y=gy, z=-0.95)]
        # 背景で回る歯車
        self.gears = []
        for g in range(7):
            gx = self.cx + rng.uniform(-4.5, 4.5)
            gy = rng.uniform(self.bottom + 0.5, self.top - 0.5)
            gr = rng.uniform(0.35, 0.8)
            col = [C(214, 170, 90), C(190, 190, 200), C(200, 120, 90)][g % 3]
            teeth = int(gr * 16)
            parts = [cylinder(gr, 0.08, col, seg=24), cylinder(gr * 0.3, 0.1, tuple(v * 0.7 for v in col), seg=12)]
            for k in range(teeth):
                a = k / teeth * math.tau
                parts += transform([box(0.12, 0.08, 0.14, col)], translate(gr * math.cos(a), 0, gr * math.sin(a)) @ rot_y(-a))
            parts = transform(parts, np.array([[1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], "f4"))
            self.gears.append((f"gear{g}", parts, (gx, gy, -0.86), rng.choice([-1, 1]) * rng.uniform(0.4, 1.0) / gr))
        wall += [box(16, 0.2, 3, C(200, 170, 130), x=self.cx, y=self.bottom - 1.2, z=0.5)]
        self.r = Renderer(W, H)
        self.r.add_mesh("static", to_array(m.statics + wall))
        for key, parts, _ in m.dyn:
            self.r.add_mesh(key, to_array(parts))
        for key, parts, _, _ in self.gears:
            self.r.add_mesh(key, to_array(parts))
        for i, (c1, c2) in enumerate(m.ball_cols):
            self.r.add_mesh(f"ball{i}", to_array([marble_parts(c1, c2)]))
        conf = [C(240, 90, 90), C(250, 200, 80), C(110, 190, 230), C(140, 210, 120), C(220, 130, 220)]
        for i, c in enumerate(conf):
            self.r.add_mesh(f"conf{i}", to_array([box(0.08, 0.02, 0.05, c, glow=0.3)]))
        rng = np.random.default_rng(seed + 7)
        self.confetti = [dict(v=(rng.normal(0, 1.4), rng.uniform(3.5, 6.0), rng.normal(0.6, 0.8)),
                              spin=rng.uniform(4, 12), ax=rng.normal(size=3), c=i % len(conf),
                              t0=m.goal_t + 0.1 + rng.uniform(0, 0.3)) for i in range(90)]
        self._precompute()
        self.fonts = {k: ImageFont.truetype(FONT, s, index=0) for k, s in (("big", 100), ("mid", 64), ("small", 48),
                                                                            ("goal", 150))}
        self._cache = {}

    # ---- ビー玉の位置(全フレーム分を先に計算)
    def ball_pos(self, b, t):
        segs = [s for s in self.m.segs if s.ball == b]
        if t <= segs[0].t0:
            return segs[0].fn(0.0), False
        for s in segs:
            if s.t0 <= t <= s.t1:
                return s.fn((t - s.t0) / max(1e-6, s.t1 - s.t0)), s.roll
        last = max(segs, key=lambda s: s.t1)
        return last.fn(1.0), False

    def active_ball(self, t):
        act = 0
        for s in self.m.segs:
            if s.t0 <= t and s.t1 - s.t0 < 30 and s.t0 > INTRO - 0.5:
                act = s.ball if s.t0 <= t else act
        return act

    def _precompute(self):
        n = int(self.duration * FPS) + 2
        nb = len(self.m.ball_cols)
        self.pos = np.zeros((nb, n, 3))
        self.rolling = np.zeros((nb, n), bool)
        for b in range(nb):
            for f in range(n):
                p, r = self.ball_pos(b, f / FPS)
                self.pos[b, f], self.rolling[b, f] = p, r
        # 回転(転がった距離 / 半径)
        self.rot = []
        for b in range(nb):
            mats = [np.eye(4, dtype="f4")]
            for f in range(1, n):
                v = self.pos[b, f] - self.pos[b, f - 1]
                dist = np.linalg.norm(v)
                if dist > 1e-5:
                    axis = np.cross((0, 1, 0), v)
                    if np.linalg.norm(axis) < 1e-6:
                        axis = (1, 0, 0)
                    mats.append(rot_axis(axis, dist / R) @ mats[-1])
                else:
                    mats.append(mats[-1])
            self.rot.append(mats)
        # カメラの注目点: いま動いているビー玉を、少し先回りしてなめらかに追う
        act = np.array([self.active_ball(f / FPS) for f in range(n)])
        focus = np.array([self.pos[act[f], min(n - 1, f + 5)] for f in range(n)])
        k = np.exp(-0.5 * (np.arange(-24, 25) / 9.0) ** 2)
        k /= k.sum()
        pad = np.pad(focus, ((24, 24), (0, 0)), mode="edge")
        self.focus = np.stack([np.convolve(pad[:, i], k, mode="valid") for i in range(3)], axis=1)
        self.speed = np.array([np.linalg.norm(self.pos[act[f], min(n - 1, f + 1)] - self.pos[act[f], f]) * FPS
                               for f in range(n)])
        self.rolling_act = np.array([self.rolling[act[f], f] for f in range(n)])

    def camera(self, t):
        f = min(len(self.focus) - 1, int(t * FPS))
        fx, fy, fz = self.focus[f]
        off = np.array((2.0, 1.7, 7.6))
        for a, b, o in self.m.cams:
            k = min(1.0, max(0.0, (t - (a - 0.6)) / 0.6)) * min(1.0, max(0.0, ((b + 0.6) - t) / 0.6))
            k = k * k * (3 - 2 * k)
            off = off * (1 - k) + np.array(o) * k
        follow_eye = np.array((fx, fy, fz)) + off
        follow_tg = np.array((fx, fy - 0.15, fz))
        mid_y = (self.top + self.bottom) / 2
        tan_v = math.tan(math.radians(34) / 2)
        need = max((self.top - self.bottom) / 2 / tan_v, (self.width / 2 + 0.8) / (tan_v * W / H))
        wide_eye = np.array((self.cx + 1.5, mid_y + 1.0, need * 1.05))
        wide_tg = np.array((self.cx, mid_y, 0.0))
        def sm(a, b, t):
            p = min(1.0, max(0.0, (t - a) / (b - a)))
            return p * p * (3 - 2 * p)
        w = 1 - sm(INTRO - 0.9, INTRO + 0.6, t)
        w = max(w, sm(self.m.goal_t + 1.6, self.m.goal_t + 3.6, t))
        eye = follow_eye * (1 - w) + wide_eye * w
        tg = follow_tg * (1 - w) + wide_tg * w
        return tuple(eye), tuple(tg), math.radians(34)

    def render_raw(self, t):
        m = self.m
        f = min(self.pos.shape[1] - 1, int(round(t * FPS)))
        draws = [("static", np.eye(4, dtype="f4"))]
        for key, _, fn in m.dyn:
            draws.append((key, fn(t)))
        for key, _, pos, spd in self.gears:
            draws.append((key, translate(*pos) @ rot_z(t * spd)))
        for b in range(len(m.ball_cols)):
            p = self.pos[b, f]
            draws.append((f"ball{b}", translate(*p) @ self.rot[b][f]))
        for c in self.confetti:
            age = t - c["t0"]
            if 0 <= age < 3.5:
                v = c["v"]
                p = (m.goal_pos[0] + v[0] * age, m.goal_pos[1] + 0.3 + v[1] * age - 4.5 * age * age, m.goal_pos[2] + v[2] * age)
                if p[1] > self.bottom - 1:
                    draws.append((f"conf{c['c']}", translate(*p) @ rot_axis(c["ax"], age * c["spin"]) @ scale(1.6, 1.6, 1.6)))
        eye, tg, fov = self.camera(t)
        light = dict(sun_dir=(0.45, 0.9, 0.75), sun_col=(0.78, 0.74, 0.68), sky=(0.5, 0.51, 0.56),
                     ground=(0.4, 0.35, 0.32), lamps=[], glow=0.4, shadow_extent=6.5, center=tg, shadow_floor=0.45,
                     spec={f"ball{i}": 1.2 for i in range(len(m.ball_cols))}, spec_default=0.18)
        raw = self.r.render(draws, eye, tg, fov, light, m.theme["bg"])
        return Image.frombytes("RGB", (W, H), raw).transpose(Image.FLIP_TOP_BOTTOM)

    # ---- 後処理(ブルーム・ミニチュア風のボケ・色味)
    def post(self, img: Image.Image, t) -> Image.Image:
        small = img.resize((W // 4, H // 4), Image.BILINEAR)
        a = np.asarray(small, dtype=np.float32) / 255
        bright = np.clip(a - 0.9, 0, 1) * 3.0
        bl = Image.fromarray((bright * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(6)).resize((W, H), Image.BILINEAR)
        blur = img.filter(ImageFilter.GaussianBlur(7))
        base = np.asarray(img, dtype=np.float32)
        bb = np.asarray(blur, dtype=np.float32)
        yy = np.arange(H)[:, None, None]
        wide = self._wide_amount(t)
        focus_band = 360 + 900 * wide
        mask = np.clip((np.abs(yy - H * 0.52) - focus_band) / 420, 0, 1) * 0.85
        out = base * (1 - mask) + bb * mask
        out += np.asarray(bl, dtype=np.float32) * 0.4
        out = 255 * ((out / 255) ** 0.96)
        out[..., 0] *= 1.02
        out[..., 2] *= 0.97
        return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))

    def _wide_amount(self, t):
        g = self.m.goal_t
        a = 1 - min(1.0, max(0.0, (t - (INTRO - 0.9)) / 1.5))
        b = min(1.0, max(0.0, (t - (g + 1.6)) / 2.0))
        return max(a, b)

    # ---- 文字
    def _text(self, key, lines, y, font, color=(255, 255, 255), stroke=0):
        if key in self._cache:
            return self._cache[key]
        im = Image.new("RGBA", (W, H))
        d = ImageDraw.Draw(im)
        f = self.fonts[font]
        for i, ln in enumerate(lines):
            d.text((W // 2, y + i * int(f.size * 1.3)), ln, font=f, fill=color + (255,), anchor="mm",
                   stroke_width=stroke, stroke_fill=(90, 50, 40, 255))
        sh = Image.new("RGBA", (W, H), (60, 40, 40, 0))
        sh.putalpha(im.getchannel("A").point(lambda v: v * 120 // 255))
        sh = sh.filter(ImageFilter.GaussianBlur(10))
        out = Image.new("RGBA", (W, H))
        out.alpha_composite(sh, (0, 8))
        out.alpha_composite(im)
        self._cache[key] = out
        return out

    def label(self, text):
        key = ("label", text)
        if key not in self._cache:
            f = self.fonts["small"]
            w = int(ImageDraw.Draw(Image.new("L", (1, 1))).textlength(text, font=f)) + 70
            im = Image.new("RGBA", (w, 96))
            d = ImageDraw.Draw(im)
            d.rounded_rectangle((0, 0, w - 1, 95), 48, fill=(255, 255, 255, 225))
            d.text((w // 2, 48), text, font=f, fill=(90, 70, 80), anchor="mm")
            self._cache[key] = im
        return self._cache[key]

    def overlay(self, img: Image.Image, t) -> Image.Image:
        img = img.convert("RGBA")
        g = self.m.goal_t

        def put(lay, a, b, pos=(0, 0), scale_in=False):
            if a <= t < b:
                al = min(1.0, (t - a) / 0.3) * (1 - min(1.0, max(0.0, (t - (b - 0.4)) / 0.4)))
                l2 = lay.copy()
                l2.putalpha(l2.getchannel("A").point(lambda v: int(v * al)))
                img.alpha_composite(l2, pos)
        put(self._text("intro", ["このビー玉、", "ゴールできる？"], 280, "big"), 0.2, INTRO + 0.3)
        put(self._text("goal", ["GOAL!!"], 330, "goal", (255, 236, 120), 6), g + 0.1, self.duration + 1)
        put(self._text("ask", ["どの仕掛けが", "好きだった？"], 1560, "mid"), g + 2.4, self.duration + 1)
        for i, (lt, text) in enumerate(self.m.labels):
            if lt < INTRO:
                continue
            lay = self.label(text)
            put(lay, lt, lt + 1.6, ((W - lay.width) // 2, 1660))
        return img

    def render(self, t):
        return self.overlay(self.post(self.render_raw(t), t), t).convert("RGB")

    # ---- 音
    def audio(self):
        n = int(SR * self.duration)
        mix = np.zeros(n, dtype=np.float32)

        def add(sig, t, g=1.0):
            i = int(t * SR)
            j = min(n, i + sig.size)
            if 0 <= i < n:
                mix[i:j] += sig[: j - i] * g

        # 転がる音: 速さに合わせたゴロゴロ
        rumble = band_noise(n, 90, 900, 1) * 0.6 + band_noise(n, 900, 3000, 2) * 0.15
        fr = np.arange(len(self.speed)) / FPS
        env = np.interp(np.arange(n) / SR, fr, np.clip(self.speed / 4.0, 0, 1) * self.rolling_act)
        k = int(SR * 0.03)
        env = np.convolve(env, np.ones(k) / k, mode="same")
        mix += rumble * env * 0.35
        rng = np.random.default_rng(3)
        for t, kind, val in self.m.sounds:
            if kind == "note":                     # 木琴(マリンバ風)
                s = tone([val * 2], 0.9, 7, (1.0, 0.0, 0.0, 0.25))
                hit = tone([val * 8], 0.15, 40, (1.0,))
                s[: hit.size] += hit * 0.15
                add(s, t, 0.5)
            elif kind == "clack":
                add(sfx("tok", 20 + int(val)), t, 0.6)
            elif kind == "tick":
                add(tone([rng.uniform(1700, 2300)], 0.05, 70, (1.0, 0.3)) +
                    band_noise(int(SR * 0.05), 2000, 8000, int(val)) * np.exp(-np.arange(int(SR * 0.05)) / (SR * 0.006)) * 0.4,
                    t, 0.45)
            elif kind == "click":
                add(tone([2400], 0.04, 90, (1.0,)), t, 0.4)
            elif kind == "thunk":
                add(sfx("thud", 5), t, 0.5)
            elif kind == "whoosh":
                add(sfx("whoosh", 9 + int(val)), t, 0.8)
            elif kind in ("whirr", "swirl"):
                dur = float(val)
                nn = int(SR * dur)
                tt = np.arange(nn) / SR
                f = 160 + 380 * (tt / dur) ** (2 if kind == "swirl" else 1)
                s = np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.15 + band_noise(nn, 400, 2500, 4) * 0.25
                add((s * np.minimum(1, tt / 0.2) * np.minimum(1, (dur - tt) / 0.2)).astype(np.float32), t, 0.5)
            elif kind == "bell":
                add(tone([1046.5, 1568.0], 2.5, 1.8, (1.0, 0.4, 0.2)), t, 0.5)
                add(tone([523.3, 659.3, 784.0, 1046.5], 2.8, 1.3, (1.0, 0.2)), t + 0.25, 0.45)
                add(band_noise(int(SR * 1.5), 2000, 9000, 77) * np.exp(-np.arange(int(SR * 1.5)) / (SR * 0.4)), t + 0.1, 0.18)
        # ひかえめな BGM(明るいコード)
        chords = [[261.6, 329.6, 392.0], [293.7, 349.2, 440.0], [329.6, 392.0, 493.9], [349.2, 440.0, 523.3]]
        t, i = 0.0, 0
        while t < self.m.goal_t:
            add(tone(chords[i % 4], 2.2, 1.2, (1.0, 0.15)), t, 0.06)
            t += 2.0
            i += 1
        fade = int(SR * 1.2)
        mix[-fade:] *= np.linspace(1, 0, fade)
        mix /= max(1e-9, np.abs(mix).max()) / 0.9
        return mix


def make_video(out_path, seed=0) -> Path:
    v = MarbleVideo(seed)
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
    for f in range(int(v.duration * FPS)):
        proc.stdin.write(v.render(f / FPS).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg の書き出しに失敗しました")
    wav.unlink()
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("out", nargs="?", default="miniature3d/output/marble.mp4")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--preview", type=float, nargs="*")
    a = p.parse_args()
    if a.preview:
        v = MarbleVideo(a.seed)
        print("modules:", v.m.seq, "melody:", v.m.melody, f"duration: {v.duration:.1f}s goal: {v.m.goal_t:.1f}s")
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        for t in a.preview:
            t0 = time.time()
            v.render(t).save(out / f"marble_{t:05.2f}.png")
            print(f"{t:5.2f}s  {time.time() - t0:.2f}s/frame")
        return
    print(make_video(a.out, a.seed))


if __name__ == "__main__":
    main()
