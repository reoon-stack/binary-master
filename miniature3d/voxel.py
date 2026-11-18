"""ブロックで何を作っているでしょう？(3D ボクセル組み立て)

  python -m miniature3d.voxel out.mp4
  python -m miniature3d.voxel out_dir --preview 3 10 18 23 28

ブロックが下の段から 1 個ずつ落ちてきて、何かの形になっていく。
顔(目・鼻)は最後に置くので、最後の最後で正体がわかる。
題材は「形(楕円体・球・円すい・曲線)+ 色」の組み合わせで決める → 別の題材も同じ仕組みで作れる。
"""

from __future__ import annotations

import argparse
import math
import subprocess
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .mesh import box, cylinder, to_array
from .render import Renderer, rot_y, scale, translate
from .scene import FONT, band_noise, ease, sfx, tone, write_wav

W, H, FPS, DURATION = 1080, 1920, 30, 30.0
SR = 44100
VS = 0.2                        # ブロック 1 個の大きさ
BUILD_A, BUILD_B = 2.6, 21.0    # 本体を組み立てる時間
DETAIL_A, DETAIL_B = 21.4, 22.6 # 顔のパーツを置く時間
FALL = 0.32


def C(r, g, b):
    return (r / 255, g / 255, b / 255)


ORANGE, ORANGE_D = C(250, 172, 84), C(226, 132, 60)
WHITE, PINK, BLACK = C(250, 246, 238), C(240, 150, 160), C(40, 34, 40)


# ------------------------------------------------------------------ 題材: ねこ

def cat_voxels(k=1.3):
    """{(x, y, z): (色, 顔パーツか)}。形は「設計座標」で決め、k 倍の細かさでブロックにする。"""
    vox = {}

    def ell(q, c, r):
        return sum(((q[i] - c[i]) / r[i]) ** 2 for i in range(3)) <= 1.0

    R = int(9 * k)
    for x in range(-R, R + 1):
        for y in range(0, int(18 * k) + 1):
            for z in range(-R, R + 1):
                q = (x / k, y / k, z / k)            # 設計座標
                col = None
                # おしり(下が広い)と胸
                if ell(q, (0, 3.2, -0.6), (4.6, 3.6, 4.0)) or ell(q, (0, 6.3, 0.4), (3.3, 3.2, 3.0)):
                    col = ORANGE
                    if q[2] > 1.6 and abs(q[0]) < 2.0 and 3.5 < q[1] < 8.5:
                        col = WHITE                 # おなか
                    elif q[2] < 0.5 and int(q[1] * 1.1) % 3 == 0:
                        col = ORANGE_D              # 背中のしま
                # 前足
                for sx in (-1, 1):
                    if ell(q, (1.5 * sx, 0.9, 3.1), (1.2, 0.9, 1.5)) or ell(q, (1.4 * sx, 2.6, 2.6), (0.9, 1.9, 0.9)):
                        col = WHITE
                # 頭(大きめ、ほっぺ広め)
                if ell(q, (0, 11.0, 0.6), (4.4, 3.6, 3.6)):
                    col = ORANGE
                    if q[2] > 2.6 and q[1] < 10.6 and abs(q[0]) < 2.3:
                        col = WHITE                 # 口のまわり
                    elif q[1] > 12.6 and abs(q[0]) < 1.4 and int(abs(q[0]) * 2) % 2 == 0:
                        col = ORANGE_D              # おでこのしま
                # 耳(三角)
                for sx in (-1, 1):
                    ex = 2.6 * sx
                    if 13.2 <= q[1] <= 16.6 and abs(q[0] - ex) <= (16.6 - q[1]) * 0.62 and abs(q[2] - 0.4) <= 0.9:
                        inner = abs(q[0] - ex) <= (16.6 - q[1]) * 0.33 and q[2] > 0.3 and q[1] < 15.6
                        col = PINK if inner else ORANGE
                if col:
                    vox[(x, y, z)] = (col, False)
    # しっぽ(体の横を回って前へ)
    pts = [(3.8, 1.0, -3.0), (5.2, 1.0, -1.0), (5.4, 1.0, 1.2), (4.8, 1.6, 3.0), (3.6, 2.6, 3.8)]
    for a, b in zip(pts, pts[1:]):
        for j in range(16):
            c = [(a[i] + (b[i] - a[i]) * j / 16) * k for i in range(3)]
            rr = 0.85 * k
            for x in range(int(c[0] - rr) - 1, int(c[0] + rr) + 2):
                for y in range(max(0, int(c[1] - rr) - 1), int(c[1] + rr) + 2):
                    for z in range(int(c[2] - rr) - 1, int(c[2] + rr) + 2):
                        if math.dist((x, y, z), c) <= rr and (x, y, z) not in vox:
                            vox[(x, y, z)] = (ORANGE_D if (x + z) % 3 == 0 else ORANGE, False)

    # 顔パーツ(最後に置く): 頭の一番手前のブロックを差し替える
    def set_front(xd, yd, col):
        x, y = round(xd * k), round(yd * k)
        zs = [zz for (xx, yy, zz) in vox if xx == x and yy == y]
        if zs:
            vox[(x, y, max(zs))] = (col, True)

    for sx in (-1, 1):
        for (dx, dy) in ((0, 0), (0.75, 0), (0, 0.75), (0.75, 0.75), (0, -0.75), (0.75, -0.75)):
            set_front(1.6 * sx + dx * sx - 0.35 * sx, 11.6 + dy, BLACK)
        set_front(1.6 * sx - 0.35 * sx, 12.35, WHITE)          # 目のハイライト
    set_front(0, 10.4, PINK)
    set_front(-0.75, 9.6, BLACK)
    set_front(0.75, 9.6, BLACK)
    return vox


# ------------------------------------------------------------------ 組み立て順

class Build:
    def __init__(self, vox):
        rng = np.random.default_rng(3)
        body = [(p, c) for p, (c, d) in vox.items() if not d]
        detail = [(p, c) for p, (c, d) in vox.items() if d]
        # 下の段から。同じ段の中は、角度の順にぐるっと(少しランダム)
        body.sort(key=lambda pc: (pc[0][1], math.atan2(pc[0][2], pc[0][0]) + rng.uniform(0, 0.8)))
        n = len(body)
        self.items = []
        for i, (p, c) in enumerate(body):
            self.items.append(dict(p=p, c=c, t=BUILD_A + (BUILD_B - BUILD_A) * (i / n) ** 0.9))
        for i, (p, c) in enumerate(detail):
            self.items.append(dict(p=p, c=c, t=DETAIL_A + (DETAIL_B - DETAIL_A) * i / max(1, len(detail) - 1),
                                   detail=True))
        # 顔パーツの場所にある本体ブロックは、目より前に見えないように除く
        self.items.sort(key=lambda it: it["t"])
        self.land = [it["t"] + FALL for it in self.items]
        self.layers = sorted({it["p"][1] for it in self.items if not it.get("detail")})

    def world(self, p):
        return (p[0] * VS, p[1] * VS + 0.3, p[2] * VS)


def voxel_mesh(build: Build):
    parts = []
    for it in build.items:
        x, y, z = build.world(it["p"])
        parts.append(box(VS * 0.94, VS * 0.94, VS * 0.94, it["c"], x=x, y=y, z=z))
    return to_array(parts)


class VoxelVideo:
    def __init__(self, answer="ねこ"):
        self.answer = answer
        self.build = Build(cat_voxels())
        self.r = Renderer(W, H)
        self.r.add_mesh("all", voxel_mesh(self.build))
        colors = sorted({it["c"] for it in self.build.items})
        self.color_key = {}
        for i, c in enumerate(colors):
            self.r.add_mesh(f"cube{i}", to_array([box(VS * 0.94, VS * 0.94, VS * 0.94, c, y=-VS * 0.47)]))
            self.color_key[c] = f"cube{i}"
        table = [cylinder(2.6, 0.22, C(196, 146, 102), y=0.0, seg=32),
                 cylinder(2.7, 0.08, C(150, 104, 72), y=-0.02, seg=32),
                 cylinder(2.45, 0.02, C(214, 168, 120), y=0.22, seg=32)]
        self.r.add_mesh("table", to_array(table))
        self.r.add_mesh("spark", to_array([box(1, 1, 1, (1.0, 0.97, 0.85), y=-0.5, glow=1.0)]))
        self.total = len(self.build.items)
        self.fonts = {k: ImageFont.truetype(FONT, s, index=0) for k, s in (("big", 96), ("mid", 64), ("small", 46))}
        self._cache = {}

    def camera(self, t):
        fov = math.radians(30)
        dist = (6.2 / 2) / (math.tan(fov / 2) * W / H)
        th = math.radians(28 - 40 * ease(t, 0, 23) + 372 * ease(t, 23.2, 26.0))   # 最後は正面
        ph = math.radians(22)
        ty = 2.2
        return (dist * math.cos(ph) * math.sin(th), ty + dist * math.sin(ph), dist * math.cos(ph) * math.cos(th)), \
            (0, ty, 0), fov

    def render(self, t):
        b = self.build
        settled = int(np.searchsorted(np.array(b.land), t, side="right"))
        draws = [("table", np.eye(4, dtype="f4")), ("all", np.eye(4, dtype="f4"), settled * 36)]
        for it in b.items[settled:]:
            if it["t"] > t:
                break
            p = (t - it["t"]) / FALL
            x, y, z = b.world(it["p"])
            drop = (1 - p) ** 2 * 2.2
            draws.append((self.color_key[it["c"]], translate(x, y + drop + VS * 0.47, z)))
        # 着地のきらきら(顔パーツと最後の 1 個)
        for it in b.items:
            if it.get("detail"):
                age = t - (it["t"] + FALL)
                if 0 <= age < 0.5:
                    x, y, z = b.world(it["p"])
                    for k in range(5):
                        a = k * 1.256 + it["p"][1]
                        kk = 0.06 * (1 - age / 0.5)
                        draws.append(("spark", translate(x + math.cos(a) * age * 1.6, y + 0.2 + age * 1.2,
                                                         z + 0.3 + math.sin(a) * age * 1.0) @ scale(kk, kk, kk)))
        eye, target, fov = self.camera(t)
        light = dict(sun_dir=(0.35, 1.0, 0.9), sun_col=(1.0, 0.95, 0.88), sky=(0.66, 0.68, 0.74),
                     ground=(0.5, 0.45, 0.42), lamps=[], glow=0.3, shadow_extent=4.5,
                     flash=0.08 * math.exp(-max(0, t - 22.95) * 6) * (t > 22.95))
        bg = ((0.78, 0.9, 0.98), (0.98, 0.86, 0.8))
        raw = self.r.render(draws, eye, target, fov, light, bg)
        img = Image.frombytes("RGB", (W, H), raw).transpose(Image.FLIP_TOP_BOTTOM).convert("RGBA")
        return self.overlay(img, t, settled).convert("RGB")

    # ---- 文字

    def _text(self, key, lines, y, font, color=(255, 255, 255)):
        if key in self._cache:
            return self._cache[key]
        im = Image.new("RGBA", (W, H))
        d = ImageDraw.Draw(im)
        f = self.fonts[font]
        for i, ln in enumerate(lines):
            d.text((W // 2, y + i * int(f.size * 1.35)), ln, font=f, fill=color + (255,), anchor="mm")
        sh = Image.new("RGBA", (W, H), (60, 50, 70, 0))
        sh.putalpha(im.getchannel("A").point(lambda v: v * 110 // 255))
        sh = sh.filter(ImageFilter.GaussianBlur(10))
        out = Image.new("RGBA", (W, H))
        out.alpha_composite(sh, (0, 8))
        out.alpha_composite(im)
        self._cache[key] = out
        return out

    def counter(self, n):
        im = Image.new("RGBA", (420, 96))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((0, 0, 419, 95), 48, fill=(255, 255, 255, 220))
        d.text((210, 48), f"ブロック {n:,} 個", font=self.fonts["small"], fill=(80, 70, 90), anchor="mm")
        return im

    def overlay(self, img, t, settled):
        def put(lay, a, b):
            if a <= t < b:
                al = ease(t, a, a + 0.35) * (1 - ease(t, b - 0.4, b))
                l2 = lay.copy()
                l2.putalpha(l2.getchannel("A").point(lambda v: int(v * al)))
                img.alpha_composite(l2)
        put(self._text("intro", ["何を作ってる", "でしょう？"], 300, "big"), 0.2, 3.4)
        put(self._text("hint", ["顔ができたら", "わかるかも…？"], 300, "mid"), 18.5, 21.2)
        put(self._text("ans", [f"正解は…「{self.answer}」！"], 300, "big"), 25.6, 31)
        put(self._text("ask", ["どこでわかった？", "コメントで教えてね"], 1600, "mid"), 26.4, 31)
        if 2.8 <= t < 23.2:
            c = self.counter(settled)
            al = ease(t, 2.8, 3.2) * (1 - ease(t, 22.8, 23.2))
            c.putalpha(c.getchannel("A").point(lambda v: int(v * al)))
            img.alpha_composite(c, ((W - c.width) // 2, 1640))
        return img

    # ---- 音

    def audio(self):
        n = int(SR * DURATION)
        mix = np.zeros(n, dtype=np.float32)

        def add(sig, t, g=1.0):
            i = int(t * SR)
            j = min(n, i + sig.size)
            if 0 <= i < n:
                mix[i:j] += sig[: j - i] * g

        # 着地のカチカチ(雨音のように)
        rng = np.random.default_rng(1)
        tick_bank = [tone([rng.uniform(1800, 2600)], 0.05, 90, (1.0,)) * 0.5 for _ in range(12)]
        for i, it in enumerate(self.build.items):
            if not it.get("detail"):
                add(tick_bank[i % 12], it["t"] + FALL, 0.12)
        # 1 段できるごとに、音階をのぼる音
        scale_hz = [261.6, 293.7, 329.6, 392.0, 440.0, 523.3, 587.3, 659.3, 784.0, 880.0, 1046.5, 1174.7,
                    1318.5, 1568.0, 1760.0, 2093.0, 2349.3, 2637.0, 3136.0]
        layers = {}
        for it in self.build.items:
            if not it.get("detail"):
                layers[it["p"][1]] = max(layers.get(it["p"][1], 0), it["t"] + FALL)
        for k, y in enumerate(sorted(layers)):
            add(tone([scale_hz[k % len(scale_hz)]], 0.9, 4.5, (1.0, 0.3, 0.1)), layers[y], 0.22)
        # 顔のパーツ: ポン
        for it in self.build.items:
            if it.get("detail"):
                add(sfx("pop", int(it["t"] * 100)), it["t"] + FALL, 0.8)
        # BGM(やさしいパッド)
        chords = [[261.6, 329.6, 392.0], [220.0, 261.6, 329.6], [174.6, 220.0, 261.6], [196.0, 246.9, 293.7]]
        t = 0.0
        k = 0
        while t < 23:
            add(tone(chords[k % 4], 3.2, 0.9, (1.0, 0.15)), t, 0.1)
            t += 3.0
            k += 1
        add(tone([523.3, 659.3, 784.0, 1046.5], 2.8, 1.4, (1.0, 0.2)), 23.1, 0.5)
        add(band_noise(int(SR * 2), 6000, 14000, 99) * np.exp(-np.arange(int(SR * 2)) / (SR * 0.6)), 23.15, 0.05)
        add(sfx("cat", 5), 26.0, 1.2)
        fade = int(SR * 1.0)
        mix[-fade:] *= np.linspace(1, 0, fade)
        mix /= max(1e-9, np.abs(mix).max()) / 0.9
        return mix


def make_video(out_path) -> Path:
    v = VoxelVideo()
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    wav = out.with_suffix(".wav")
    write_wav(wav, v.audio())
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", str(wav), "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
           "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
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
    p.add_argument("out", nargs="?", default="miniature3d/output/voxel.mp4")
    p.add_argument("--preview", type=float, nargs="*")
    a = p.parse_args()
    if a.preview:
        v = VoxelVideo()
        print("blocks:", v.total)
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        for t in a.preview:
            t0 = time.time()
            v.render(t).save(out / f"voxel_{t:05.2f}.png")
            print(f"{t:5.2f}s  {time.time() - t0:.2f}s/frame")
        return
    print(make_video(a.out))


if __name__ == "__main__":
    main()
