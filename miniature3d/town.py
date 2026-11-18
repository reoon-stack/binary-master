"""ちいさな町の 1 日(タイムラプス)。朝 5 時から夜 24 時までを 30 秒で。

  python -m miniature3d.town out.mp4
  python -m miniature3d.town out_dir --preview 1 8 16 22 28

島の上に家・木・環状道路・時計台・灯台・桟橋。太陽が動いて影が回り、
夕方に窓と街灯がひとつずつ灯り、夜は星が出る。車・人・船・雲が動き続ける。
"""

from __future__ import annotations

import argparse
import math
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .mesh import box, cone, cylinder, sphere, to_array, transform
from .render import Renderer, rot_y, scale, translate
from .scene import FONT, band_noise, ease, tone, write_wav

W, H, FPS, DURATION = 1080, 1920, 30, 30.0
SR = 44100


def C(r, g, b):
    return (r / 255, g / 255, b / 255)


GRASS, GRASS_D = C(132, 190, 104), C(104, 160, 86)
SAND = C(236, 214, 160)
WATER = C(96, 176, 214)
ROAD = C(118, 118, 128)
CREAM = C(244, 234, 214)
WARM_WIN = C(255, 214, 120)


def hour_at(t):
    return 5.0 + 19.0 * min(1.0, t / 28.0)


def keyframe(h, frames):
    """時刻 h での値を、(時刻, 値) の表から補間する。"""
    for (h0, v0), (h1, v1) in zip(frames, frames[1:]):
        if h0 <= h <= h1:
            p = (h - h0) / (h1 - h0)
            p = p * p * (3 - 2 * p)
            return tuple(a + (b - a) * p for a, b in zip(v0, v1))
    return frames[-1][1] if h > frames[-1][0] else frames[0][1]


SKY_TOP = [(5, (0.32, 0.36, 0.62)), (7.5, (0.45, 0.68, 0.96)), (15, (0.45, 0.70, 0.98)),
           (17.5, (0.42, 0.36, 0.64)), (19.5, (0.06, 0.08, 0.2)), (24, (0.04, 0.05, 0.15))]
SKY_BOT = [(5, (0.98, 0.70, 0.56)), (7.5, (0.80, 0.92, 1.0)), (15, (0.86, 0.93, 1.0)),
           (17.5, (1.0, 0.58, 0.42)), (19.5, (0.2, 0.18, 0.38)), (24, (0.14, 0.12, 0.28))]
SUN_COL = [(5, (0.7, 0.45, 0.35)), (7.5, (1.0, 0.95, 0.86)), (15, (1.0, 0.94, 0.84)),
           (17.5, (1.0, 0.58, 0.34)), (19.0, (0.25, 0.25, 0.4)), (24, (0.16, 0.2, 0.34))]
AMB_SKY = [(5, (0.4, 0.38, 0.5)), (8, (0.56, 0.6, 0.7)), (15, (0.56, 0.6, 0.7)),
           (17.5, (0.5, 0.4, 0.5)), (19.5, (0.14, 0.16, 0.28)), (24, (0.12, 0.13, 0.25))]
AMB_GND = [(5, (0.3, 0.26, 0.3)), (8, (0.44, 0.42, 0.36)), (15, (0.44, 0.42, 0.36)),
           (17.5, (0.36, 0.28, 0.28)), (19.5, (0.08, 0.08, 0.12)), (24, (0.07, 0.07, 0.1))]


def night(h):
    return min(1.0, max(0.0, (h - 17.8) / 1.8))


@dataclass
class Obj:
    key: str
    parts: list
    model: object = None          # 時刻 → 行列(動くもの)。None なら固定
    on: float = 0.0               # この時刻(時)から見える
    off: float = 99.0


def ring_pos(r, a, y=0.0):
    return (r * math.cos(a), y, r * math.sin(a))


def facing(a):
    """円周上の角度 a で、中心を向く回転。"""
    return rot_y(-a - math.pi / 2)


def house(w, h, d, wall, roof, seed):
    rng = np.random.default_rng(seed)
    parts = [box(w, h, d, wall), box(w + 0.06, 0.06, d + 0.06, C(200, 190, 176))]
    rh = 0.5 + 0.15 * rng.random()
    parts += transform([cone(max(w, d) * 0.78, rh, roof, y=h, seg=4)], rot_y(math.pi / 4))
    parts += [box(0.22, 0.42, 0.03, C(140, 90, 64), z=d / 2 + 0.01)]
    windows, lit = [], []
    for x in (-w * 0.28, w * 0.28):
        windows.append(box(0.22, 0.22, 0.03, C(120, 150, 180), x=x, y=h * 0.55, z=d / 2 + 0.01))
        lit.append(box(0.22, 0.22, 0.035, WARM_WIN, x=x, y=h * 0.55, z=d / 2 + 0.012, glow=1.0))
    for z in (-d * 0.2, d * 0.2):
        windows.append(box(0.03, 0.22, 0.2, C(120, 150, 180), x=w / 2 + 0.01, y=h * 0.55, z=z))
        lit.append(box(0.035, 0.22, 0.2, WARM_WIN, x=w / 2 + 0.012, y=h * 0.55, z=z, glow=1.0))
    return parts + windows, lit


def car_parts(col):
    return [box(0.5, 0.16, 0.28, col, y=0.05), box(0.28, 0.14, 0.24, C(220, 236, 246), y=0.21, x=-0.03),
            box(0.03, 0.05, 0.06, C(255, 250, 220), x=0.25, y=0.1, z=-0.08, glow=1.0),
            box(0.03, 0.05, 0.06, C(255, 250, 220), x=0.25, y=0.1, z=0.08, glow=1.0)] + \
           [cylinder(0.05, 0.04, C(40, 40, 46), x=x, y=0.0, z=z, seg=6) for x in (-0.15, 0.15) for z in (-0.15, 0.15)]


def build_town():
    objs: list[Obj] = []
    add = objs.append
    lamps = []

    add(Obj("water", [cylinder(6.6, 0.1, WATER, y=-0.42, seg=28),
                      cylinder(5.0, 0.11, C(130, 200, 226), y=-0.42, seg=28)]))
    add(Obj("island", [cylinder(4.75, 0.4, SAND, y=-0.4, seg=24), cylinder(4.3, 0.42, GRASS, y=-0.4, seg=24),
                       cylinder(4.32, 0.04, GRASS_D, y=-0.02, seg=24, r_top=4.3)]))
    road = []
    for i in range(24):
        a = i / 24 * math.tau
        road += transform([box(0.75, 0.04, 0.6, ROAD, y=0.0)], translate(*ring_pos(2.6, a)) @ facing(a))
        if i % 2 == 0:
            road += transform([box(0.3, 0.045, 0.05, C(240, 236, 220), y=0.0)],
                              translate(*ring_pos(2.6, a)) @ facing(a) @ rot_y(math.pi / 2))
    add(Obj("road", road))
    add(Obj("plaza", [cylinder(1.25, 0.04, C(230, 214, 186), seg=16), cylinder(0.5, 0.15, C(200, 190, 176), seg=12),
                      cylinder(0.4, 0.16, C(120, 190, 230), seg=12)]))

    # 時計台
    tower = [box(0.7, 2.2, 0.7, CREAM, y=0.15), box(0.8, 0.12, 0.8, C(210, 196, 176), y=2.35)]
    tower += transform([cone(0.66, 0.8, C(196, 90, 80), y=2.47, seg=4)], rot_y(math.pi / 4))
    for k in range(4):
        tower += transform([cylinder(0.22, 0.03, C(250, 248, 240), seg=12)],
                           rot_y(k * math.pi / 2) @ translate(0, 1.85, 0.36) @ np.array(
                               [[1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], "f4"))
    add(Obj("tower", tower))
    tower_glow = []
    for k in range(4):
        tower_glow += transform([cylinder(0.2, 0.035, C(255, 240, 190), seg=12, glow=1.0)],
                                rot_y(k * math.pi / 2) @ translate(0, 1.85, 0.37) @ np.array(
                                    [[1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], "f4"))
    add(Obj("tower_glow", tower_glow, on=18.3))

    # 家(外周)
    walls = [C(244, 196, 170), C(176, 214, 230), C(250, 228, 160), C(200, 226, 180), C(236, 200, 220),
             C(240, 240, 232), C(214, 196, 240), C(250, 210, 150)]
    roofs = [C(200, 90, 80), C(80, 120, 170), C(150, 96, 70), C(90, 140, 100), C(170, 80, 110),
             C(120, 110, 100), C(110, 90, 160), C(190, 120, 60)]
    angles = [0.2, 1.0, 1.75, 2.5, 3.3, 4.2, 5.0, 5.75]
    lit_times = [17.6, 18.9, 18.1, 19.6, 17.9, 18.5, 19.2, 18.3]
    for i, a in enumerate(angles):
        w, hh, d = 0.95 + 0.25 * (i % 3) / 2, 0.75 + 0.3 * ((i * 5) % 3) / 2, 0.85
        parts, lit = house(w, hh, d, walls[i], roofs[i], i)
        m = translate(*ring_pos(3.55, a)) @ facing(a)
        add(Obj(f"house{i}", transform(parts, m)))
        add(Obj(f"lit{i}", transform(lit, m), on=lit_times[i]))

    # 木
    rng = np.random.default_rng(4)
    trees = []
    for i in range(14):
        a = rng.uniform(0, math.tau)
        r = rng.choice([rng.uniform(1.45, 1.95), rng.uniform(3.0, 3.15), rng.uniform(4.0, 4.15)])
        x, _, z = ring_pos(r, a)
        if rng.random() < 0.5:
            trees += [cylinder(0.06, 0.25, C(130, 90, 60), x=x, z=z, seg=6),
                      cone(0.28, 0.75, C(70, 140, 80), x=x, y=0.2, z=z, seg=7)]
        else:
            trees += [cylinder(0.06, 0.25, C(130, 90, 60), x=x, z=z, seg=6),
                      sphere(0.26, C(110, 176, 90), x=x, y=0.48, z=z, seg=7, rings=4)]
    add(Obj("trees", trees))

    # 街灯
    poles, heads = [], []
    for i in range(6):
        a = i / 6 * math.tau + 0.26
        x, _, z = ring_pos(2.05, a)
        poles += [cylinder(0.035, 0.9, C(70, 70, 80), x=x, z=z, seg=6),
                  sphere(0.08, C(240, 236, 220), x=x, y=0.95, z=z, seg=6, rings=4)]
        heads.append(((x, 1.0, z), 18.0 + 0.18 * i))
    add(Obj("poles", poles))
    for i, ((x, y, z), on) in enumerate(heads):
        add(Obj(f"lamp{i}", [sphere(0.085, C(255, 226, 150), x=x, y=y - 0.05, z=z, seg=6, rings=4, glow=1.0)], on=on))
        lamps.append(((x, y, z), on))

    # 灯台と桟橋
    la = 2.2
    lx, _, lz = ring_pos(4.05, la)
    light_house = [cylinder(0.32, 0.5, C(244, 244, 240), x=lx, z=lz, seg=10, r_top=0.29),
                   cylinder(0.29, 0.5, C(220, 70, 70), x=lx, y=0.5, z=lz, seg=10, r_top=0.26),
                   cylinder(0.26, 0.5, C(244, 244, 240), x=lx, y=1.0, z=lz, seg=10, r_top=0.23),
                   cylinder(0.32, 0.06, C(60, 60, 70), x=lx, y=1.5, z=lz, seg=10),
                   cylinder(0.18, 0.3, C(190, 220, 230), x=lx, y=1.56, z=lz, seg=8),
                   cone(0.26, 0.25, C(220, 70, 70), x=lx, y=1.86, z=lz, seg=8)]
    add(Obj("lighthouse", light_house))
    add(Obj("lighthouse_on", [cylinder(0.185, 0.3, C(255, 240, 180), x=lx, y=1.56, z=lz, seg=8, glow=1.0)], on=18.6))
    lamps.append(((lx, 1.75, lz), 18.6))
    pa = 4.6
    pier = []
    for k in range(5):
        x, _, z = ring_pos(4.4 + k * 0.32, pa)
        pier += transform([box(0.3, 0.06, 0.7, C(170, 120, 80), y=-0.08)], translate(x, 0, z) @ facing(pa))
        pier += [cylinder(0.04, 0.4, C(120, 84, 60), x=x, y=-0.4, z=z, seg=5)]
    add(Obj("pier", pier))

    # 動くもの: 車・船・人・雲
    car_cols = [C(230, 80, 80), C(80, 140, 220), C(250, 200, 80)]
    for i, col in enumerate(car_cols):
        def m(t, i=i):
            a = i * math.tau / 3 + t * (0.32 + 0.04 * i)
            lane = 2.47 if i % 2 == 0 else 2.73
            return translate(*ring_pos(lane, a, 0.02)) @ rot_y(-a)
        add(Obj(f"car{i}", car_parts(col), model=m))

    def boat_m(t):
        a = 4.9 + t * 0.12
        return translate(*ring_pos(5.55, a, -0.33)) @ rot_y(-a) @ translate(0, 0.02 * math.sin(t * 4), 0)
    add(Obj("boat", [box(0.7, 0.14, 0.3, C(244, 244, 240)), box(0.3, 0.16, 0.22, C(220, 90, 80), y=0.14),
                     cylinder(0.02, 0.5, C(120, 90, 70), y=0.14, seg=5)], model=boat_m))

    shirt = [C(230, 100, 100), C(90, 150, 220), C(250, 190, 80), C(120, 190, 120), C(200, 120, 200)]
    for i in range(5):
        def pm(t, i=i):
            a = i * math.tau / 5 + t * (0.18 if i % 2 else -0.15)
            r = 1.05 if i < 3 else 3.0
            return translate(*ring_pos(r, a, 0.04 + 0.015 * abs(math.sin(t * 9 + i)))) @ rot_y(-a)
        add(Obj(f"person{i}", [cylinder(0.07, 0.18, shirt[i], y=0.0, seg=6),
                               sphere(0.06, C(240, 200, 170), y=0.25, seg=6, rings=4)], model=pm, off=21.5))

    for i in range(3):
        def cm(t, i=i):
            x = ((t * 0.25 + i * 4.5) % 13) - 6.5
            return translate(x, 4.2 + 0.4 * i, -2.0 + 2.2 * i)
        rng2 = np.random.default_rng(10 + i)
        cloud = [sphere(rng2.uniform(0.35, 0.55), C(250, 250, 252), x=k * 0.45, y=0.1 * (k % 2), seg=7, rings=4)
                 for k in range(4)]
        add(Obj(f"cloud{i}", cloud, model=cm, off=18.6))
    return objs, lamps


class Town:
    def __init__(self):
        self.objs, self.lamps = build_town()
        self.r = Renderer(W, H)
        for o in self.objs:
            self.r.add_mesh(o.key, to_array(o.parts))
        self.font_big = ImageFont.truetype(FONT, 96, index=0)
        self.font_mid = ImageFont.truetype(FONT, 64, index=0)
        self.font_clock = ImageFont.truetype(FONT, 54, index=0)
        self._clock_cache = {}

    def camera(self, t):
        fov = math.radians(30)
        dist = (11.2 / 2) / (math.tan(fov / 2) * W / H)
        th = math.radians(20 + 70 * t / DURATION)
        ph = math.radians(34)
        return (dist * math.cos(ph) * math.sin(th), 0.6 + dist * math.sin(ph), dist * math.cos(ph) * math.cos(th)), \
            (0, 0.6, 0), fov

    def light(self, t):
        h = hour_at(t)
        nf = night(h)
        if h < 18.5:
            sh = (h - 6) / 12 * math.pi
            el = max(0.12, math.sin(sh))
            sun = (math.cos(sh) * 0.9, el * 1.2, -0.45)
        else:
            sun = (-0.4, 0.9, 0.5)
        lamps = []
        for pos, on in self.lamps:
            k = ease(h, on, on + 0.25)
            if k > 0:
                lamps.append((pos, (1.5 * k, 1.0 * k, 0.5 * k)))
        for o in self.objs:
            if o.key.startswith("car") and nf > 0.3:
                m = o.model(t)
                p = m @ np.array([0.45, 0.15, 0, 1], "f4")
                lamps.append((tuple(p[:3]), (0.35 * nf, 0.32 * nf, 0.24 * nf)))
        return dict(sun_dir=sun, sun_col=keyframe(h, SUN_COL), sky=keyframe(h, AMB_SKY),
                    ground=keyframe(h, AMB_GND), lamps=lamps, glow=nf, shadow_extent=7.5, falloff=3.2)

    def clock_label(self, h):
        hh, mm = int(h) % 24, int((h % 1) * 60) // 10 * 10
        key = (hh, mm)
        if key not in self._clock_cache:
            text = f"{hh:d}:{mm:02d}"
            im = Image.new("RGBA", (260, 110))
            d = ImageDraw.Draw(im)
            d.rounded_rectangle((0, 0, 259, 109), 55, fill=(255, 255, 255, 215))
            d.text((130, 55), text, font=self.font_clock, fill=(70, 60, 80), anchor="mm")
            self._clock_cache[key] = im
        return self._clock_cache[key]

    def text_layer(self, lines, y, font):
        im = Image.new("RGBA", (W, H))
        d = ImageDraw.Draw(im)
        for i, ln in enumerate(lines):
            d.text((W // 2, y + i * int(font.size * 1.35)), ln, font=font, fill="white", anchor="mm")
        sh = Image.new("RGBA", (W, H), (30, 30, 60, 0))
        sh.putalpha(im.getchannel("A").point(lambda v: v * 120 // 255))
        sh = sh.filter(ImageFilter.GaussianBlur(10))
        out = Image.new("RGBA", (W, H))
        out.alpha_composite(sh, (0, 8))
        out.alpha_composite(im)
        return out

    def render(self, t) -> Image.Image:
        h = hour_at(t)
        draws = []
        for o in self.objs:
            if not (o.on <= h < o.off):
                continue
            m = o.model(t) if o.model else np.eye(4, dtype="f4")
            if o.off < 99 and h > o.off - 0.8:          # 雲や人は夕方に少しずつ消える
                k = max(0.001, (o.off - h) / 0.8)
                m = m @ scale(k, k, k)
            draws.append((o.key, m))
        eye, target, fov = self.camera(t)
        bg = (keyframe(h, SKY_TOP), keyframe(h, SKY_BOT), night(h), t)
        raw = self.r.render(draws, eye, target, fov, self.light(t), bg)
        img = Image.frombytes("RGB", (W, H), raw).transpose(Image.FLIP_TOP_BOTTOM).convert("RGBA")
        if not hasattr(self, "_intro"):
            self._intro = self.text_layer(["ちいさな町の", "1日"], 300, self.font_big)
            self._ask = self.text_layer(["どの時間が", "いちばん好き？"], 1540, self.font_mid)
        for lay, a, b in ((self._intro, 0.2, 3.3), (self._ask, 26.0, 31)):
            if a <= t < b:
                al = ease(t, a, a + 0.4) * (1 - ease(t, b - 0.5, b))
                l2 = lay.copy()
                l2.putalpha(l2.getchannel("A").point(lambda v: int(v * al)))
                img.alpha_composite(l2)
        if t >= 2.8:
            lab = self.clock_label(h).copy()
            al = ease(t, 2.8, 3.3)
            lab.putalpha(lab.getchannel("A").point(lambda v: int(v * al)))
            img.alpha_composite(lab, ((W - lab.width) // 2, 140))
        return img.convert("RGB")


# ------------------------------------------------------------------ 音

def chirp(seed):
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(rng.integers(2, 5)):
        n = int(SR * rng.uniform(0.05, 0.1))
        t = np.arange(n) / SR
        f0 = rng.uniform(2800, 4200)
        f = f0 + rng.uniform(600, 1500) * np.sin(np.pi * t / t[-1])
        s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.sin(np.pi * t / t[-1]) ** 2
        out.append(s)
        out.append(np.zeros(int(SR * rng.uniform(0.03, 0.08))))
    return np.concatenate(out).astype(np.float32)


def crickets(n, seed):
    rng = np.random.default_rng(seed)
    t = np.arange(n) / SR
    carrier = np.sin(2 * np.pi * 4600 * t)
    pulses = (np.sin(2 * np.pi * 30 * t) > 0.6).astype(np.float32)
    gate = (np.sin(2 * np.pi * 1.6 * t + rng.uniform(0, 6)) > 0.2).astype(np.float32)
    return (carrier * pulses * gate).astype(np.float32)


def music_box(seconds):
    notes = [523.3, 659.3, 784.0, 880.0, 784.0, 659.3, 587.3, 659.3,
             523.3, 587.3, 659.3, 784.0, 659.3, 523.3, 440.0, 392.0]
    out = np.zeros(int(SR * (seconds + 3)), dtype=np.float32)
    step = 60 / 92 / 2
    t, i = 0.0, 0
    while t < seconds:
        s = tone([notes[i % len(notes)]], 1.2, 3.5, (1.0, 0.3, 0.08, 0.05))
        j = int(t * SR)
        out[j:j + s.size] += s[: out.size - j] * 0.25
        if i % 4 == 0:
            pad = tone([notes[i % len(notes)] / 4, notes[i % len(notes)] / 2], step * 4, 1.0, (1.0, 0.2))
            out[j:j + pad.size] += pad[: out.size - j] * 0.12
        t += step
        i += 1
    return out[: int(SR * seconds)]


def build_audio() -> np.ndarray:
    n = int(SR * DURATION)
    mix = music_box(DURATION) * 0.9
    mix += band_noise(n, 80, 600, 1) * 0.03                       # 風
    rng = np.random.default_rng(7)
    for _ in range(26):
        t = rng.uniform(0.5, 15.5)
        s = chirp(int(t * 100)) * 0.18
        i = int(t * SR)
        mix[i:i + s.size] += s[: n - i]
    times = np.arange(n) / SR
    hours = np.array([hour_at(x) for x in times[::441]])
    nf = np.interp(times, times[::441], np.clip((hours - 18.6) / 1.5, 0, 1))
    mix += crickets(n, 3) * nf * 0.05
    for i in range(8):                                             # 灯りが点く小さな音
        t = (17.6 + i * 0.25 - 5) / 19 * 28
        s = tone([1568 + 200 * (i % 3)], 0.3, 14, (1.0, 0.2)) * 0.12
        j = int(t * SR)
        mix[j:j + s.size] += s[: n - j]
    s = tone([523.3, 659.3, 784.0, 1046.5], 2.5, 1.6, (1.0, 0.2)) * 0.45
    j = int(26.0 * SR)
    mix[j:j + s.size] += s[: n - j]
    fade = int(SR * 1.2)
    mix[:fade] *= np.linspace(0, 1, fade)
    mix[-fade:] *= np.linspace(1, 0, fade)
    mix /= max(1e-9, np.abs(mix).max()) / 0.9
    return mix


def make_video(out_path) -> Path:
    town = Town()
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    wav = out.with_suffix(".wav")
    write_wav(wav, build_audio())
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", str(wav), "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
           "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
           "-shortest", "-movflags", "+faststart", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for f in range(int(DURATION * FPS)):
        proc.stdin.write(town.render(f / FPS).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg の書き出しに失敗しました")
    wav.unlink()
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("out", nargs="?", default="miniature3d/output/town.mp4")
    p.add_argument("--preview", type=float, nargs="*")
    a = p.parse_args()
    if a.preview:
        town = Town()
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        for t in a.preview:
            t0 = time.time()
            town.render(t).save(out / f"town_{t:05.2f}.png")
            print(f"{t:5.2f}s  {time.time() - t0:.2f}s/frame")
        return
    print(make_video(a.out))


if __name__ == "__main__":
    main()
