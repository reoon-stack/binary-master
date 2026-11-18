"""ミニチュア部屋づくり動画: アニメーション・カメラ・照明・文字・音を組み立てて MP4 にする。

  python -m miniature3d out.mp4
  python -m miniature3d out_dir --preview 3 10 20 28
"""

from __future__ import annotations

import math
import subprocess
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .mesh import box, to_array
from .render import Renderer, rot_y, scale, translate
from .room import LAMP_POS, ROOM_SPAN, build_room

W, H, FPS, DURATION = 1080, 1920, 30, 30.0
SR = 44100
FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"


def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def ease(t, a, b):
    p = clamp((t - a) / (b - a))
    return p * p * (3 - 2 * p)


def back_out(p, s=1.9):
    p -= 1
    return 1 + p * p * ((s + 1) * p + s)


def bounce_out(p):
    n, d = 7.5625, 2.75
    if p < 1 / d:
        return n * p * p
    if p < 2 / d:
        p -= 1.5 / d
        return n * p * p + 0.75
    if p < 2.5 / d:
        p -= 2.25 / d
        return n * p * p + 0.9375
    p -= 2.625 / d
    return n * p * p + 0.984375


def lerp(a, b, p):
    return tuple(x + (y - x) * p for x, y in zip(a, b))


# ------------------------------------------------------------------ 映像

class Scene:
    def __init__(self):
        self.items = build_room()
        self.r = Renderer(W, H)
        self.pivot = {}
        for it in self.items:
            arr = to_array(it.parts)
            self.r.add_mesh(it.key, arr)
            v = arr.reshape(-1, 10)
            self.pivot[it.key] = ((v[:, 0].min() + v[:, 0].max()) / 2, v[:, 1].min(),
                                  (v[:, 2].min() + v[:, 2].max()) / 2,
                                  v[:, 1].max())
        self.r.add_mesh("spark", to_array([box(1, 1, 1, (1.0, 0.97, 0.85), y=-0.5, glow=1.0)]))
        rng = np.random.default_rng(5)
        self.sparks = []
        for it in self.items:
            if not it.spark:
                continue
            land = self.land_time(it)
            px, py, pz, top = self.pivot[it.key]
            for _ in range(7):
                a = rng.uniform(0, math.tau)
                self.sparks.append(dict(t0=land, x=it.pos[0] + px, y=it.pos[1] + py + 0.1, z=it.pos[2] + pz,
                                        vx=math.cos(a) * rng.uniform(1.2, 2.4), vz=math.sin(a) * rng.uniform(1.2, 2.4),
                                        vy=rng.uniform(1.5, 3.0), s=rng.uniform(0.06, 0.11)))
        self.texts = self._make_texts()

    @staticmethod
    def land_time(it):
        return it.t + {"drop": 0.33, "jump": 0.8, "rise": 0.5}.get(it.anim, 0.05)

    def item_model(self, it, t):
        if t < it.t or t >= it.until:
            return None
        p = t - it.t
        px, py, pz, _ = self.pivot[it.key]
        x, y, z = it.pos
        sx = sy = sz = 1.0
        if it.anim == "drop":
            q = clamp(p / 0.6)
            y += 4.0 * (1 - bounce_out(q))
            if 0.3 < p < 0.55:
                k = math.sin((p - 0.3) / 0.25 * math.pi) * 0.12
                sy, sx, sz = 1 - k, 1 + k * 0.6, 1 + k * 0.6
        elif it.anim == "pop":
            s = back_out(clamp(p / 0.45))
            sx = sy = sz = max(0.001, s)
        elif it.anim == "rise":
            sy = max(0.001, back_out(clamp(p / 0.75), 1.2))
        elif it.anim == "jump":
            q = clamp(p / 0.8)
            start = (x + 2.6, 0.08, z + 2.2)
            x, z = start[0] + (x - start[0]) * q, start[2] + (z - start[2]) * q
            y = start[1] + (y - start[1]) * q + 2.0 * math.sin(math.pi * q)
            if 0.78 < p < 1.05:
                k = math.sin((p - 0.78) / 0.27 * math.pi) * 0.18
                sy, sx, sz = 1 - k, 1 + k * 0.5, 1 + k * 0.5
            elif p > 1.2:
                sy = 1 + 0.03 * math.sin((p - 1.2) * 3)        # ねこの呼吸
        m = translate(x + px, y + py, z + pz) @ scale(sx, sy, sz) @ translate(-px, -py, -pz)
        if it.anim == "jump" and p < 0.8:
            m = m @ translate(px, py, pz) @ rot_y(-0.6 * (1 - clamp(p / 0.8))) @ translate(-px, -py, -pz)
        return m

    def light(self, t):
        e = ease(t, 20.8, 22.6)
        lamp = ease(t, 21.9, 22.25)
        flash = 0.06 * math.exp(-max(0, t - 21.95) * 8) * (t > 21.95)
        return dict(
            sun_dir=lerp((0.55, 1.0, 0.4), (0.2, 0.6, 0.9), e),
            sun_col=lerp((0.95, 0.9, 0.82), (0.22, 0.2, 0.34), e),
            sky=lerp((0.56, 0.58, 0.66), (0.22, 0.22, 0.38), e),
            ground=lerp((0.44, 0.38, 0.33), (0.18, 0.14, 0.2), e),
            lamp_pos=LAMP_POS, lamp_col=(1.4, 0.95, 0.55), lamp=lamp * 1.25,
            glow=0.12 + 0.9 * lamp, flash=flash,
        )

    def background(self, t):
        e = ease(t, 20.8, 22.6)
        top = lerp((1.0, 0.88, 0.76), (0.24, 0.23, 0.42), e)
        bottom = lerp((0.98, 0.7, 0.66), (0.52, 0.34, 0.5), e)
        return top, bottom

    def camera(self, t):
        fov = math.radians(30)
        tan_h = math.tan(fov / 2) * W / H
        dist = (ROOM_SPAN / 2) / tan_h
        dist *= 1.18 - 0.18 * ease(t, 0, 4) + 0.06 * ease(t, 24, 30)
        th = math.radians(36 + 16 * ease(t, 0, 21) + 22 * ease(t, 23.5, 30))
        ph = math.radians(31 - 3 * ease(t, 0, 21) + 4 * ease(t, 23.5, 30))
        tx, ty, tz = 0.0, 1.25, 0.0
        eye = (tx + dist * math.cos(ph) * math.sin(th), ty + dist * math.sin(ph), tz + dist * math.cos(ph) * math.cos(th))
        return eye, (tx, ty, tz), fov

    def _make_texts(self):
        def layer(lines, size, y):
            im = Image.new("RGBA", (W, H))
            d = ImageDraw.Draw(im)
            f = ImageFont.truetype(FONT, size, index=0)
            yy = y
            for ln, sz in lines:
                ff = ImageFont.truetype(FONT, sz, index=0) if sz != size else f
                d.text((W // 2, yy), ln, font=ff, fill=(255, 255, 255, 255), anchor="mm")
                yy += int(sz * 1.35)
            sh = Image.new("RGBA", (W, H), (60, 30, 40, 0))
            sh.putalpha(im.getchannel("A").point(lambda v: v * 120 // 255))
            sh = sh.filter(ImageFilter.GaussianBlur(10))
            out = Image.new("RGBA", (W, H))
            out.alpha_composite(sh, (0, 8))
            out.alpha_composite(im)
            return out
        return {
            "intro": layer([("ちいさな部屋を", 92), ("つくってみた", 92)], 92, 300),
            "done": layer([("完成！", 120)], 120, 300),
            "ask": layer([("こんな部屋、", 64), ("住んでみたい？", 64)], 64, 1560),
        }

    def overlay(self, frame: Image.Image, t):
        for key, a, b in (("intro", 0.2, 3.4), ("done", 24.6, 31), ("ask", 25.4, 31)):
            if a <= t < b:
                alpha = ease(t, a, a + 0.35) * (1 - ease(t, b - 0.5, b))
                if alpha <= 0:
                    continue
                lay = self.texts[key]
                if alpha < 1:
                    lay = lay.copy()
                    lay.putalpha(lay.getchannel("A").point(lambda v: int(v * alpha)))
                frame.alpha_composite(lay)
        return frame

    def render(self, t) -> Image.Image:
        draws = []
        for it in self.items:
            m = self.item_model(it, t)
            if m is not None:
                draws.append((it.key, m))
        for s in self.sparks:
            age = t - s["t0"]
            if 0 <= age < 0.55:
                k = s["s"] * (1 - age / 0.55)
                pos = (s["x"] + s["vx"] * age, s["y"] + s["vy"] * age - 4 * age * age, s["z"] + s["vz"] * age)
                draws.append(("spark", translate(*pos) @ rot_y(age * 8) @ scale(k, k, k)))
        eye, target, fov = self.camera(t)
        raw = self.r.render(draws, eye, target, fov, self.light(t), self.background(t))
        img = Image.frombytes("RGB", (W, H), raw).transpose(Image.FLIP_TOP_BOTTOM).convert("RGBA")
        return self.overlay(img, t).convert("RGB")


# ------------------------------------------------------------------ 音

def band_noise(n, lo, hi, seed):
    rng = np.random.default_rng(seed)
    f = np.fft.rfft(rng.standard_normal(n))
    fr = np.fft.rfftfreq(n, 1 / SR)
    f[(fr < lo) | (fr > hi)] = 0
    y = np.fft.irfft(f, n)
    return (y / (np.abs(y).max() + 1e-9)).astype(np.float32)


def tone(freqs, dur, decay=6.0, harm=(1.0, 0.35, 0.12)):
    t = np.arange(int(SR * dur)) / SR
    s = np.zeros_like(t)
    for f in freqs:
        for k, a in enumerate(harm, 1):
            s += a * np.sin(2 * np.pi * f * k * t)
    env = np.minimum(1, t / 0.01) * np.exp(-t * decay)
    return (s * env / max(1, len(freqs))).astype(np.float32)


def sfx(kind, seed):
    rng = np.random.default_rng(seed)
    if kind == "plank":
        f = rng.uniform(560, 820)
        return tone([f], 0.18, 28) * 0.6 + band_noise(int(SR * 0.18), 1500, 6000, seed) * np.exp(-np.arange(int(SR * 0.18)) / (SR * 0.01)) * 0.25
    if kind == "tok":
        f = rng.uniform(240, 360)
        return tone([f], 0.3, 18) * 0.8 + band_noise(int(SR * 0.3), 300, 3000, seed) * np.exp(-np.arange(int(SR * 0.3)) / (SR * 0.03)) * 0.3
    if kind == "thud":
        return tone([90], 0.5, 9) * 1.0 + band_noise(int(SR * 0.5), 60, 800, seed) * np.exp(-np.arange(int(SR * 0.5)) / (SR * 0.06)) * 0.4
    if kind == "whoosh":
        n = int(SR * 0.8)
        s = band_noise(n, 300, 5000, seed) * np.sin(np.linspace(0, np.pi, n)) ** 2
        return s * 0.35
    if kind == "pop":
        n = int(SR * 0.14)
        t = np.arange(n) / SR
        f = rng.uniform(380, 520) * (1 + 1.6 * t / t[-1])
        return (np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 30) * 0.5).astype(np.float32)
    if kind == "soft":
        n = int(SR * 0.25)
        return band_noise(n, 80, 900, seed) * np.exp(-np.arange(n) / (SR * 0.05)) * 0.6
    if kind == "book":
        return tone([rng.uniform(1100, 1500)], 0.08, 60) * 0.3
    if kind == "cat":
        n = int(SR * 0.42)
        t = np.arange(n) / SR
        f = 620 + 380 * np.sin(np.pi * t / t[-1]) + 15 * np.sin(2 * np.pi * 7 * t)
        ph = 2 * np.pi * np.cumsum(f) / SR
        s = np.sin(ph) + 0.5 * np.sin(2 * ph) + 0.25 * np.sin(3 * ph)
        env = np.minimum(1, t / 0.04) * np.minimum(1, (t[-1] - t) / 0.12)
        return (s * env * 0.18).astype(np.float32)
    return np.zeros(1, dtype=np.float32)


def bgm(seconds):
    """ゆったりした Lo-Fi 風(78 BPM、Fmaj7 → Em7 → Dm7 → Cmaj7)。"""
    beat = 60 / 78
    chords = [[174.6, 220.0, 261.6, 329.6], [164.8, 196.0, 246.9, 293.7],
              [146.8, 174.6, 220.0, 261.6], [130.8, 164.8, 196.0, 246.9]]
    out = np.zeros(int(SR * (seconds + 3)), dtype=np.float32)

    def add(sig, t, g):
        i = int(t * SR)
        j = min(out.size, i + sig.size)
        out[i:j] += sig[: j - i] * g

    t, k = 0.0, 0
    rng = np.random.default_rng(3)
    melody = [523.3, 587.3, 659.3, 784.0, 659.3, 587.3, 523.3, 440.0]
    while t < seconds:
        ch = chords[k % 4]
        add(tone(ch, beat * 4, 1.1, (1.0, 0.25, 0.08)), t, 0.22)
        add(tone([ch[0] / 2], beat * 2, 2.0), t, 0.25)
        add(tone([ch[0] / 2], beat * 2, 2.0), t + beat * 2, 0.2)
        for b in range(4):
            add(tone([60], 0.25, 18, (1.0,)), t + b * beat, 0.35 if b % 2 == 0 else 0.0)
            n = int(SR * 0.05)
            add(band_noise(n, 6000, 12000, int(t * 10) + b) * np.exp(-np.arange(n) / (SR * 0.01)),
                t + b * beat + beat / 2, 0.05)
        if k % 2 == 1:
            for i in range(3):
                add(tone([melody[(k * 3 + i) % len(melody)]], beat * 1.5, 3.0, (1.0, 0.1)), t + i * beat * 1.2, 0.08)
        t += beat * 4
        k += 1
    out = out[: int(SR * seconds)]
    out += band_noise(out.size, 1000, 8000, 9) * 0.006       # レコードのノイズ
    crackle = np.zeros_like(out)
    for i in rng.integers(0, out.size, int(seconds * 6)):
        crackle[i:i + 30] += rng.uniform(0.05, 0.15)
    out += crackle * band_noise(out.size, 2000, 9000, 11)
    fade = int(SR * 1.5)
    out[:fade] *= np.linspace(0, 1, fade)
    out[-fade:] *= np.linspace(1, 0, fade)
    return out


def build_audio(sc: Scene) -> np.ndarray:
    n = int(SR * DURATION)
    mix = bgm(DURATION) * 0.8

    def add(sig, t, g=1.0):
        i = int(t * SR)
        j = min(n, i + sig.size)
        if 0 <= i < n:
            mix[i:j] += sig[: j - i] * g

    for i, it in enumerate(sc.items):
        if it.sound:
            when = it.t if it.sound == "whoosh" else sc.land_time(it)
            add(sfx(it.sound, i + 1), when, 0.9)
    add(tone([2600], 0.05, 80, (1.0,)) * 0.5, 21.95)                      # スタンドのカチッ
    add(tone([523.3, 659.3, 784.0, 1046.5], 2.5, 1.6, (1.0, 0.2)) * 0.6, 24.6)
    add(band_noise(int(SR * 2), 6000, 14000, 99) * np.exp(-np.arange(int(SR * 2)) / (SR * 0.6)) * 0.05, 24.65)
    mix /= max(1e-9, np.abs(mix).max()) / 0.9
    return mix


def write_wav(path, x):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())


def make_video(out_path) -> Path:
    sc = Scene()
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    wav = out.with_suffix(".wav")
    write_wav(wav, build_audio(sc))
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", str(wav), "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
           "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
           "-shortest", "-movflags", "+faststart", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for f in range(int(DURATION * FPS)):
        proc.stdin.write(sc.render(f / FPS).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg の書き出しに失敗しました")
    wav.unlink()
    return out
