"""台本 + 音声から縦型(1080x1920)の Shorts 動画を作る。

画面構成:
  上   : 進捗バー / お題の帯
  中央 : セリフに合わせた大きな絵文字(ポップアニメーション)
  下   : 字幕ボックス(話者の色) / 2人のキャラクター(口パク)
背景はゆっくり動くグラデーション + 浮かぶ光の玉。
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .audio import SR, Segment
from .content import SPEAKERS, Episode

W, H = 1080, 1920
FPS = 30

PALETTES = [
    ((255, 214, 102), (255, 138, 101)),  # オレンジ
    ((120, 210, 255), (130, 120, 255)),  # 青紫
    ((150, 235, 170), (60, 180, 200)),   # ミント
    ((255, 170, 210), (190, 130, 255)),  # ピンク
]
DARK = (40, 35, 50)

FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
]
EMOJI_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
    "/usr/share/fonts/noto/NotoColorEmoji.ttf",
]


def _first_existing(paths, env):
    if os.environ.get(env) and Path(os.environ[env]).exists():
        return os.environ[env]
    for p in paths:
        if Path(p).exists():
            return p
    return None


FONT = _first_existing(FONT_CANDIDATES, "YT_FONT_PATH")
EMOJI_FONT = _first_existing(EMOJI_FONT_CANDIDATES, "YT_EMOJI_FONT_PATH")


@lru_cache(maxsize=None)
def font(size: int):
    if not FONT:
        raise RuntimeError("日本語フォントが見つかりません (fonts-noto-cjk をインストール)")
    return ImageFont.truetype(FONT, size)


# ---------------------------------------------------------------- パーツ

@lru_cache(maxsize=None)
def emoji_image(ch: str, size: int) -> Image.Image | None:
    if not EMOJI_FONT:
        return None
    f = ImageFont.truetype(EMOJI_FONT, 109)
    im = Image.new("RGBA", (400, 160))
    ImageDraw.Draw(im).text((10, 10), ch, font=f, embedded_color=True)
    box = im.getbbox()
    if not box:
        return None
    im = im.crop(box)
    scale = size / max(im.size)
    return im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))),
                     Image.LANCZOS)


_MEASURE = ImageDraw.Draw(Image.new("L", (1, 1)))


def _wrap(text: str, f, max_w: int) -> list[str]:
    """行数が最小になる範囲で、各行の長さがそろうように折り返す。"""
    lines = _wrap_greedy(text, f, max_w)
    if len(lines) > 1:
        target = _MEASURE.textlength(text, font=f) / len(lines)
        w = int(target)
        while w < max_w:
            balanced = _wrap_greedy(text, f, w)
            if len(balanced) == len(lines):
                return balanced
            w += 10
    return lines


def _wrap_greedy(text: str, f, max_w: int) -> list[str]:
    lines, cur = [], ""
    for ch in text:
        if _MEASURE.textlength(cur + ch, font=f) > max_w:
            # 句読点・小さい文字を行頭に置かない
            if ch in "、。！？…ぁぃぅぇぉっゃゅょー」）" and cur:
                cur, ch = cur[:-1], cur[-1] + ch
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    lines.append(cur)
    return lines


def topic_banner(topic: str) -> Image.Image:
    im = Image.new("RGBA", (W, 330))
    d = ImageDraw.Draw(im)
    size = 76
    while size > 44:
        lines = _wrap(topic, font(size), W - 200)
        if len(lines) <= 2:
            break
        size -= 4
    line_h = int(size * 1.3)
    box_h = line_h * len(lines) + 70
    top = 100
    d.rounded_rectangle((60, top, W - 60, top + box_h), 36, fill=(255, 255, 255, 245),
                        outline=DARK, width=8)
    tag = "9割が知らない雑学"
    tf = font(40)
    tw = d.textlength(tag, font=tf)
    d.rounded_rectangle((W / 2 - tw / 2 - 30, top - 34, W / 2 + tw / 2 + 30, top + 34), 34,
                        fill=(235, 60, 70))
    d.text((W / 2, top), tag, font=tf, fill="white", anchor="mm")
    y = top + 40 + line_h / 2
    for ln in lines:
        d.text((W / 2, y), ln, font=font(size), fill=DARK, anchor="mm")
        y += line_h
    return im


def subtitle_box(text: str, speaker: str) -> Image.Image:
    sp = SPEAKERS[speaker]
    im = Image.new("RGBA", (W, 420))
    d = ImageDraw.Draw(im)
    size = 68
    while size > 44:
        lines = _wrap(text, font(size), W - 200)
        if len(lines) <= 3:
            break
        size -= 4
    line_h = int(size * 1.35)
    box_h = line_h * len(lines) + 90
    y0 = 60
    d.rounded_rectangle((50, y0, W - 50, y0 + box_h), 40, fill=(255, 255, 255, 240),
                        outline=sp["color"], width=10)
    nf = font(40)
    nw = d.textlength(sp["name"], font=nf)
    d.rounded_rectangle((90, y0 - 34, 90 + nw + 60, y0 + 34), 34, fill=sp["color"])
    d.text((120 + nw / 2, y0), sp["name"], font=nf, fill="white", anchor="mm")
    y = y0 + 50 + line_h / 2
    for ln in lines:
        d.text((W / 2, y), ln, font=font(size), fill=DARK, anchor="mm")
        y += line_h
    return im


def character(speaker: str, mouth_open: bool) -> Image.Image:
    """シンプルなデフォルメ顔のキャラクター(オリジナル描画)。"""
    S = 300
    im = Image.new("RGBA", (S, S + 40))
    d = ImageDraw.Draw(im)
    hair = SPEAKERS[speaker]["color"]
    cx, cy, r = S / 2, S / 2 + 20, 120
    if speaker == "z":
        # 頭の上の豆のような飾り
        for dx in (-70, 70):
            d.ellipse((cx + dx - 34, cy - r - 30, cx + dx + 34, cy - r + 40), fill=hair,
                      outline=DARK, width=5)
    else:
        # ツインテール(ドリル)
        for dx in (-r - 10, r + 10):
            d.ellipse((cx + dx - 40, cy - 10, cx + dx + 40, cy + 110), fill=hair,
                      outline=DARK, width=5)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=hair, outline=DARK, width=6)
    fr = r - 22
    d.ellipse((cx - fr, cy - fr + 26, cx + fr, cy + fr + 18), fill=(255, 232, 214))
    d.chord((cx - r + 4, cy - r + 4, cx + r - 4, cy + r - 40), 180, 360, fill=hair)  # 前髪
    for dx in (-42, 42):
        d.ellipse((cx + dx - 15, cy + 10, cx + dx + 15, cy + 50), fill=DARK)
        d.ellipse((cx + dx - 6, cy + 16, cx + dx + 4, cy + 28), fill="white")
        d.ellipse((cx + dx * 1.45 - 18, cy + 52, cx + dx * 1.45 + 18, cy + 66),
                  fill=(255, 170, 170))
    if mouth_open:
        d.ellipse((cx - 18, cy + 58, cx + 18, cy + 92), fill=(170, 50, 60), outline=DARK, width=3)
    else:
        d.arc((cx - 20, cy + 50, cx + 20, cy + 76), 20, 160, fill=DARK, width=5)
    return im


# ---------------------------------------------------------------- 背景

class Background:
    def __init__(self, seed: int):
        top, bottom = PALETTES[seed % len(PALETTES)]
        t = np.linspace(0, 1, H)[:, None]
        self.grad = (np.array(top) * (1 - t) + np.array(bottom) * t)  # (H,3)
        rng = np.random.default_rng(seed)
        self.dots = [(rng.uniform(0, W), rng.uniform(0, H), rng.uniform(20, 70),
                      rng.uniform(30, 90), rng.uniform(0, 6.28)) for _ in range(18)]

    def frame(self, t: float) -> Image.Image:
        shift = 0.06 * math.sin(t * 0.6)
        g = np.clip(self.grad * (1 + shift), 0, 255).astype(np.uint8)
        arr = np.broadcast_to(g[:, None, :], (H, W, 3)).copy()
        img = Image.fromarray(arr)
        over = Image.new("RGBA", (W, H))
        d = ImageDraw.Draw(over)
        for x, y, r, speed, ph in self.dots:
            yy = (y - t * speed) % (H + 200) - 100
            xx = x + 30 * math.sin(t * 0.8 + ph)
            d.ellipse((xx - r, yy - r, xx + r, yy + r), fill=(255, 255, 255, 50))
        img.paste(over, (0, 0), over)
        return img


# ---------------------------------------------------------------- 合成

def _ease_pop(p: float) -> float:
    """0→1 で 0 → 1.12 → 1 と弾むスケール。"""
    if p >= 1:
        return 1.0
    return 1 + 0.12 * math.sin(p * math.pi) if p > 0.6 else (p / 0.6) * 1.07


def _paste_center(base: Image.Image, im: Image.Image, cx: float, cy: float, scale: float = 1.0,
                  alpha: float = 1.0):
    if scale != 1.0:
        im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))),
                       Image.BILINEAR)
    if alpha < 1.0:
        a = im.getchannel("A").point(lambda v: int(v * alpha))
        im = im.copy()
        im.putalpha(a)
    base.paste(im, (int(cx - im.width / 2), int(cy - im.height / 2)), im)


def render_video(ep: Episode, voice: np.ndarray, audio_path: Path, segments: list[Segment],
                 total: float, out_path: Path, seed: int = 0) -> Path:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg が見つかりません")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    bg = Background(seed)
    banner = topic_banner(ep.topic)
    subs = [subtitle_box(l.text, l.speaker) for l in ep.lines]
    emojis = [emoji_image(l.emoji, 380) for l in ep.lines]
    chars = {(s, m): character(s, m) for s in SPEAKERS for m in (False, True)}
    shadow = Image.new("RGBA", (W, H))

    # 口パク用: フレームごとの声の大きさ
    hop = SR // FPS
    n_frames = int(total * FPS)
    loud = np.array([np.abs(voice[i * hop:(i + 1) * hop]).mean() if i * hop < voice.size else 0
                     for i in range(n_frames)])

    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", str(audio_path),
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart",
           str(out_path)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    char_pos = {"m": 260, "z": W - 260}
    for f in range(n_frames):
        t = f / FPS
        idx = 0
        for i, s in enumerate(segments):
            if t >= s.start - 0.05:
                idx = i
        seg, line = segments[idx], ep.lines[idx]
        p = (t - seg.start + 0.05) / 0.3
        talking = seg.start <= t <= seg.end

        frame = bg.frame(t)
        # 進捗バー
        d = ImageDraw.Draw(frame)
        d.rectangle((0, 0, W, 14), fill=(255, 255, 255))
        d.rectangle((0, 0, W * t / total, 14), fill=(235, 60, 70))

        frame.paste(banner, (0, 0), banner)

        em = emojis[idx]
        if em is not None:
            bob = 12 * math.sin(t * 3)
            _paste_center(frame, em, W / 2, 720 + bob, _ease_pop(max(0, p)))

        sub = subs[idx]
        slide = max(0.0, 1 - max(0, p) * 1.6) * 40
        _paste_center(frame, sub, W / 2, 1270 + slide, 1.0, min(1.0, max(0.0, p * 2)))

        for sp, x in char_pos.items():
            active = sp == line.speaker
            mouth = active and talking and loud[f] > 0.02 and (f // 3) % 2 == 0
            scale = 1.3 if active else 1.05
            jump = -abs(math.sin(t * 9)) * 16 if active and talking else 0
            _paste_center(frame, chars[(sp, mouth)], x, 1680 + jump, scale,
                          1.0 if active else 0.75)
        proc.stdin.write(frame.tobytes())

    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg の書き出しに失敗しました")
    return out_path
