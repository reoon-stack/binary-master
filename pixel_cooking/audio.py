"""調理音(ASMR)を工程表から合成する。すべて numpy で作るので著作権フリー。"""

from __future__ import annotations

import math
import wave

import numpy as np

from .engine import CUT1, CUT2, DURATION, Scene
from .gfx import ease

SR = 44100


def band_noise(n, lo, hi, seed):
    rng = np.random.default_rng(seed)
    x = rng.standard_normal(n)
    f = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(n, 1 / SR)
    f[(freqs < lo) | (freqs > hi)] = 0
    y = np.fft.irfft(f, n)
    return (y / (np.abs(y).max() + 1e-9)).astype(np.float32)


class Mixer:
    def __init__(self, seconds):
        self.buf = np.zeros(int(SR * seconds), dtype=np.float32)

    def add(self, sig, t, gain=1.0):
        i = int(t * SR)
        if i >= self.buf.size or i < 0:
            return
        j = min(self.buf.size, i + sig.size)
        self.buf[i:j] += sig[: j - i] * gain


def chop(seed):
    n = int(SR * 0.16)
    t = np.arange(n) / SR
    thunk = np.sin(2 * np.pi * (170 + 60 * np.exp(-t * 60)) * t) * np.exp(-t * 38)
    click = band_noise(n, 2500, 9000, seed) * np.exp(-t * 180)
    crunch = band_noise(n, 900, 5000, seed + 1) * np.exp(-t * 45) * 0.5
    return (thunk * 0.9 + click * 0.6 + crunch).astype(np.float32)


def scrape(dur, seed, lo=1500, hi=7000):
    n = int(SR * dur)
    return band_noise(n, lo, hi, seed) * np.sin(np.linspace(0, np.pi, n)) ** 0.6 * 0.25


def thud(seed):
    n = int(SR * 0.25)
    t = np.arange(n) / SR
    return (np.sin(2 * np.pi * 110 * t) * np.exp(-t * 22) * 0.6
            + band_noise(n, 200, 1800, seed) * np.exp(-t * 30) * 0.3).astype(np.float32)


def clank(seed, base=320):
    n = int(SR * 0.5)
    t = np.arange(n) / SR
    s = sum(np.sin(2 * np.pi * f * t) * a for f, a in ((base, 1), (base * 2.71, 0.5), (base * 4.4, 0.3)))
    return (s * np.exp(-t * 14) * 0.35 + band_noise(n, 2000, 8000, seed) * np.exp(-t * 90) * 0.2).astype(np.float32)


def squelch(seed, dur=0.18):
    n = int(SR * dur)
    return band_noise(n, 150, 900, seed) * np.sin(np.linspace(0, np.pi, n)) * 0.5


def pour(dur, seed):
    n = int(SR * dur)
    s = band_noise(n, 300, 3500, seed) * (1 + 0.5 * band_noise(n, 4, 18, seed + 1))
    env = np.minimum(1, np.linspace(0, 6, n)) * np.minimum(1, np.linspace(6, 0, n))
    return (s * env * 0.35).astype(np.float32)


def plop(seed):
    n = int(SR * 0.12)
    t = np.arange(n) / SR
    f = 260 + 500 * np.exp(-t * 40)
    return (np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 30) * 0.4).astype(np.float32)


def chime(freqs, step=0.12):
    n = int(SR * (2.4 + step * len(freqs)))
    out = np.zeros(n, dtype=np.float32)
    for k, f in enumerate(freqs):
        t = np.arange(n - int(SR * k * step)) / SR
        s = (np.sin(2 * np.pi * f * t) + 0.3 * np.sin(4 * np.pi * f * t)) * np.exp(-t * 2.2)
        out[int(SR * k * step):] += s.astype(np.float32) * 0.25
    return out


def sizzle_track(intensity, seed):
    n = int(SR * DURATION)
    base = band_noise(n, 2500, 11000, seed) * 0.5 + band_noise(n, 600, 2500, seed + 1) * 0.15
    rng = np.random.default_rng(seed + 2)
    pops = np.zeros(n, dtype=np.float32)
    for i in rng.integers(0, n, int(DURATION * 70)):
        ln = int(SR * rng.uniform(0.002, 0.008))
        m = min(ln, n - i)
        pops[i:i + m] += rng.uniform(0.3, 1.0) * np.exp(-np.arange(m) / (ln / 3))
    pops *= band_noise(n, 1500, 12000, seed + 3)
    env = np.interp(np.arange(n) / SR, np.linspace(0, DURATION, 600),
                    [intensity(x) for x in np.linspace(0, DURATION, 600)])
    am = 1 + 0.25 * band_noise(n, 2, 12, seed + 4)
    return ((base + pops * 1.4) * env * am).astype(np.float32)


def boil_track(intensity, seed):
    """ぐつぐつ: 低めの泡がはじける音。"""
    n = int(SR * DURATION)
    out = np.zeros(n, dtype=np.float32)
    rng = np.random.default_rng(seed)
    for _ in range(int(DURATION * 30)):
        t0 = rng.uniform(0, DURATION)
        g = intensity(t0)
        if g <= 0.01:
            continue
        ln = int(SR * rng.uniform(0.03, 0.08))
        tt = np.arange(ln) / SR
        f = rng.uniform(180, 520) * (1 + 2 * tt / tt[-1])
        b = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.sin(np.linspace(0, np.pi, ln)) * g
        i = int(t0 * SR)
        j = min(n, i + ln)
        out[i:j] += b[: j - i].astype(np.float32) * 0.35
    rumble = band_noise(n, 60, 400, seed + 5)
    env = np.interp(np.arange(n) / SR, np.linspace(0, DURATION, 600),
                    [intensity(x) for x in np.linspace(0, DURATION, 600)])
    return out + rumble * env * 0.12


def build_audio(sc: Scene) -> np.ndarray:
    m = Mixer(DURATION)
    m.add(band_noise(int(SR * DURATION), 80, 900, 1) * 0.035, 0)
    m.add(chime([523.25, 659.25, 783.99], 0.35) * 0.6, 0.15)

    for (a, b, n), g in ((CUT1, 1.0), (CUT2, 0.8)):
        for k in range(n):
            m.add(chop(100 + k + int(a * 10)), a + (b - a) * (k + 0.5) / n, 0.55 * g)
    m.add(thud(3), 3.42, 0.5)
    m.add(thud(4), 6.42, 0.5)
    for a, b in ((5.6, 6.05), (7.7, 8.1), (8.15, 8.75)):
        m.add(scrape(b - a, int(a * 10)), a, 0.8)

    liquid_t = sc.liquid_steps[0].a + 0.2 if sc.liquid_steps else None
    surges = []
    for s in sc.steps:
        if s.kind == "add":
            if s.raw[1] in ("rice", "noodles", "spaghetti", "beans"):
                m.add(band_noise(int(SR * (s.b - s.a)), 1500, 6000, int(s.a * 10))
                      * np.hanning(int(SR * (s.b - s.a))) * 0.25, s.a + 0.2)
            else:
                for k in range(4):
                    m.add(plop(int(s.a * 100) + k), s.a + 0.35 + k * 0.1, 0.6)
            surges.append((s.a + 0.35, 0.4))
        elif s.kind == "liquid":
            m.add(pour(s.b - s.a, int(s.a * 10)), s.a + 0.15, 0.9)
            surges.append((s.a + 0.3, 0.9))
        elif s.kind == "sauce":
            m.add(squelch(int(s.a * 10)), s.a + 0.3)
            m.add(squelch(int(s.a * 10) + 1), s.a + 0.5)
            surges.append((s.a + 0.35, 0.3))
        elif s.kind == "stir":
            tt = s.a
            while tt < s.b:
                m.add(scrape(0.28, int(tt * 100), 800 if sc.pot else 1500, 5000 if sc.pot else 7000), tt, 0.4)
                tt += 0.375
        elif s.kind == "shape":
            for k in range(5):
                m.add(thud(50 + k), s.a + k * 0.1, 0.3)
        elif s.kind == "egg_pour":
            m.add(pour(s.b - s.a, 77), s.a + 0.2, 0.5)
            surges.append((s.a + 0.3, 0.6))
        elif s.kind == "egg_sheet":
            m.add(chop(77) * 0.7, s.a + 0.48)
            surges.append((s.a + 0.65, 0.9))
            tt = s.a + 0.95
            while tt < s.a + 2.15:
                n = int(SR * 0.03)
                m.add(band_noise(n, 3000, 9000, int(tt * 100)) * np.exp(-np.arange(n) / (SR * 0.006)) * 0.3, tt)
                tt += 0.12

    def heat(x):
        return ease(x, 9.1, 9.9) * (1 - ease(x, 19.2, 21.2))

    def surge(x):
        return sum(g * math.exp(-max(0, x - a) * 2) * (x >= a) for a, g in surges)

    if sc.pot:
        def sizzle_i(x):
            v = heat(x) * (1 if liquid_t is None or x < liquid_t else 0.15)
            return v + 0.3 * (20.4 <= x < 25.5) * (1 - ease(x, 24.3, 25.5)) * 0.4

        def boil_i(x):
            if liquid_t is None:
                return 0
            return ease(x, liquid_t + 0.5, liquid_t + 2.0) * (1 - ease(x, 19.0, 20.5)) * (0.8 + 0.4 * surge(x))
        m.add(sizzle_track(sizzle_i, 7) * 1.1, 0)
        m.add(boil_track(boil_i, 8), 0)
    else:
        def sizzle_i(x):
            v = heat(x) * (1 - 0.35 * ease(x, 10.8, 12.0)) + surge(x) * heat(x)
            return v + 0.3 * (20.4 <= x < 25.5) * (1 - ease(x, 24.3, 25.5))
        m.add(sizzle_track(sizzle_i, 7) * 1.4, 0)

    # 盛り付け
    m.add(clank(30, 300), 20.2, 0.6)
    if sc.transfer == "pour":
        m.add(pour(0.7, 31), 20.35, 0.9)
    else:
        m.add(scrape(0.5, 32), 20.3, 0.5)
        m.add(thud(31), 20.7, 0.7)
    if sc.has_egg_pan:
        m.add(clank(33, 360), 21.9, 0.5)
        m.add(scrape(0.6, 34), 22.0, 0.45)
        m.add(thud(35), 22.55, 0.6)
    # 仕上げ
    for g, a, b in sc.garnish_schedule():
        if g[0] == "line":
            for tt in np.arange(a + 0.3, b - 0.2, 0.22):
                m.add(squelch(int(tt * 100), 0.15) * 0.6, float(tt))
        elif g[0] == "sprinkle":
            m.add(scrape(b - a - 0.4, int(a * 10), 4000, 12000) * 0.5, a + 0.25)
        else:
            m.add(thud(int(a * 10)) * 0.3, b - 0.25)
    m.add(chime([783.99, 987.77, 1174.66, 1567.98], 0.09) * 0.4, 27.3)
    sp = int(SR * 2.5)
    m.add(band_noise(sp, 6000, 14000, 99) * np.exp(-np.arange(sp) / (SR * 0.8)) * 0.06, 27.35)

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
