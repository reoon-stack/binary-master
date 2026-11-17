"""台本 + 音声から縦型(1080x1920)の「究極の2択」Shorts 動画を作る。

画面構成:
  上   : 進捗バー / 「究極の2択 Q1/3」ヘッダー
  中央 : A(赤)と B(青)の選択肢カード、間に VS(カウントダウン中は数字)
         キャラが選ぶと、そのカードに顔バッジが付く
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
from .content import SPEAKERS, Choice, Episode

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
    """句読点で区切れるならそこで改行。無理なら行の長さがそろうように折り返す。"""
    lines = _wrap_greedy(text, f, max_w)
    phrased = _wrap_phrases(text, f, max_w)
    if phrased and len(phrased) <= len(lines):
        return phrased
    if len(lines) > 1:
        target = _MEASURE.textlength(text, font=f) / len(lines)
        w = int(target)
        while w < max_w:
            balanced = _wrap_greedy(text, f, w)
            if len(balanced) == len(lines):
                return balanced
            w += 10
    return lines


def _wrap_phrases(text: str, f, max_w: int) -> list[str] | None:
    import re
    chunks = [c for c in re.split(r"(?<=[、。！？])", text) if c]
    lines, cur = [], ""
    for c in chunks:
        if _MEASURE.textlength(c, font=f) > max_w:
            return None
        if _MEASURE.textlength(cur + c, font=f) > max_w:
            lines.append(cur)
            cur = c
        else:
            cur += c
    lines.append(cur)
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


def subtitle_box(text: str, speaker: str) -> Image.Image:
    sp = SPEAKERS[speaker]
    im = Image.new("RGBA", (W, 420))
    d = ImageDraw.Draw(im)
    size = 60
    while size > 40:
        lines = _wrap(text, font(size), W - 200)
        if len(lines) <= 2:
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


RED = (235, 70, 85)
BLUE = (55, 125, 235)
CARD_W, CARD_H = W - 100, 450
CARD_Y = {"a": 560, "b": 1100}


def header(q: int, total_q: int) -> Image.Image:
    im = Image.new("RGBA", (W, 300))
    d = ImageDraw.Draw(im)
    top = 110
    d.rounded_rectangle((60, top, W - 60, top + 140), 36, fill=(255, 255, 255, 245),
                        outline=DARK, width=8)
    d.text((W / 2, top + 72), "あなたはどっち？", font=font(78), fill=DARK, anchor="mm")
    tag = f"究極の2択  Q{q + 1}/{total_q}"
    tf = font(44)
    tw = d.textlength(tag, font=tf)
    d.rounded_rectangle((W / 2 - tw / 2 - 34, top - 38, W / 2 + tw / 2 + 34, top + 38), 38,
                        fill=RED)
    d.text((W / 2, top), tag, font=tf, fill="white", anchor="mm")
    return im


def choice_card(c: Choice, side: str) -> Image.Image:
    color = RED if side == "a" else BLUE
    im = Image.new("RGBA", (CARD_W + 40, CARD_H + 40))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((20, 20, CARD_W + 20, CARD_H + 20), 50, fill=color,
                        outline="white", width=12)
    # A / B ラベル
    d.ellipse((46, 46, 166, 166), fill="white")
    d.text((106, 104), side.upper(), font=font(78), fill=color, anchor="mm")
    em = emoji_image(c.emoji, 190)
    if em:
        im.paste(em, (int((CARD_W + 40) / 2 - em.width / 2), 50), em)
    size = 84
    while size > 48:
        lines = _wrap(c.text, font(size), CARD_W - 120)
        if len(lines) <= 2:
            break
        size -= 4
    line_h = int(size * 1.25)
    y = 335 - line_h * (len(lines) - 1) / 2
    for ln in lines:
        d.text(((CARD_W + 40) / 2, y), ln, font=font(size), fill="white", anchor="mm",
               stroke_width=5, stroke_fill=DARK)
        y += line_h
    return im


def vs_badge(label: str, color=DARK) -> Image.Image:
    im = Image.new("RGBA", (220, 220))
    d = ImageDraw.Draw(im)
    d.ellipse((10, 10, 210, 210), fill="white", outline=color, width=10)
    d.text((110, 112), label, font=font(96 if len(label) == 1 else 78), fill=color, anchor="mm")
    return im


def pick_badge(speaker: str) -> Image.Image:
    sp = SPEAKERS[speaker]
    face = character(speaker, False).resize((170, 192), Image.LANCZOS)
    im = Image.new("RGBA", (260, 260))
    d = ImageDraw.Draw(im)
    d.ellipse((20, 20, 240, 240), fill="white", outline=sp["color"], width=10)
    im.paste(face, (45, 20), face)
    d.rounded_rectangle((50, 196, 210, 250), 27, fill=sp["color"])
    d.text((130, 223), "これ！", font=font(36), fill="white", anchor="mm")
    return im


def render_video(ep: Episode, voice: np.ndarray, audio_path: Path, segments: list[Segment],
                 total: float, out_path: Path, seed: int = 0) -> Path:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg が見つかりません")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    nq = len(ep.questions)
    bg = Background(seed)
    headers = [header(i, nq) for i in range(nq)]
    cards = [{s: choice_card(getattr(q, s), s) for s in "ab"} for q in ep.questions]
    subs = [subtitle_box(st.text, st.speaker) if st.kind == "line" else None for st in ep.steps]
    chars = {(s, m): character(s, m) for s in SPEAKERS for m in (False, True)}
    badges = {s: pick_badge(s) for s in SPEAKERS}
    vs = vs_badge("VS")
    nums = {k: vs_badge(str(k), RED) for k in (1, 2, 3)}

    # 各問の開始時刻(カードのスライドイン用)と、各選択の時刻
    q_start = {}
    picks = []  # (time, q, side, speaker)
    for st, seg in zip(ep.steps, segments):
        q_start.setdefault(st.q, seg.start)
        if st.pick:
            picks.append((seg.start, st.q, st.pick, st.speaker))
    q_start[0] = 0.0

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

    char_pos = {"m": 230, "z": W - 230}
    for f in range(n_frames):
        t = f / FPS
        idx = 0
        for i, sg in enumerate(segments):
            if t >= sg.start - 0.05:
                idx = i
        st, seg = ep.steps[idx], segments[idx]
        q = st.q
        talking = st.kind == "line" and seg.start <= t <= seg.end

        frame = bg.frame(t)
        d = ImageDraw.Draw(frame)
        d.rectangle((0, 0, W, 14), fill=(255, 255, 255))
        d.rectangle((0, 0, W * t / total, 14), fill=RED)
        frame.paste(headers[q], (0, 0), headers[q])

        # カード(新しい問題ではスライドイン)
        p_in = min(1.0, max(0.0, (t - q_start[q]) / 0.35)) if q > 0 else 1.0
        ease = 1 - (1 - p_in) ** 3
        chosen = {side: (pt, sp) for pt, qq, side, sp in picks if qq == q and pt <= t + 0.05}
        for side in "ab":
            off = (1 - ease) * W * (-1 if side == "a" else 1)
            sc = 1.0
            if side in chosen:
                sc = 1 + 0.05 * min(1.0, (t - chosen[side][0]) / 0.2)
            _paste_center(frame, cards[q][side], W / 2 + off, CARD_Y[side], sc)

        # 中央: カウントダウン中は数字、それ以外は VS
        if st.kind == "countdown" and seg.start <= t <= seg.end:
            k = 3 - int(t - seg.start)
            p = (t - seg.start) % 1
            _paste_center(frame, nums[max(1, k)], W / 2, 830, 1.25 - 0.25 * min(1, p / 0.25))
        else:
            _paste_center(frame, vs, W / 2, 830, 1.0 + 0.04 * math.sin(t * 4))

        # 選んだキャラの顔バッジ
        for side, (pt, sp) in chosen.items():
            pp = min(1.0, (t - pt) / 0.3)
            _paste_center(frame, badges[sp], W - 140, CARD_Y[side] - 120, _ease_pop(pp))

        sub = subs[idx]
        if sub is not None:
            p = (t - seg.start + 0.05) / 0.3
            slide = max(0.0, 1 - max(0, p) * 1.6) * 30
            _paste_center(frame, sub, W / 2, 1500 + slide, 1.0, min(1.0, max(0.0, p * 2)))

        for sp, x in char_pos.items():
            active = st.kind == "line" and sp == st.speaker
            mouth = active and talking and loud[f] > 0.02 and (f // 3) % 2 == 0
            scale = 1.0 if active else 0.85
            jump = -abs(math.sin(t * 9)) * 14 if active and talking else 0
            _paste_center(frame, chars[(sp, mouth)], x, 1775 + jump, scale,
                          1.0 if active else 0.8)
        proc.stdin.write(frame.tobytes())

    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg の書き出しに失敗しました")
    return out_path
