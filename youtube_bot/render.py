"""Episode を縦型 (1080x1920) の Shorts 動画に書き出す。Pillow + ffmpeg を使う。"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .content import Episode, Slide

W, H = 1080, 1920
FPS = 30

BG_TOP = (18, 24, 48)
BG_BOTTOM = (40, 20, 70)
TEXT = (245, 245, 250)
ACCENT = (255, 200, 60)
ANSWER = (90, 230, 160)
MUTED = (170, 175, 200)

FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "C:/Windows/Fonts/meiryob.ttc",
]


def find_font() -> str:
    env = os.environ.get("YT_FONT_PATH")
    if env and Path(env).exists():
        return env
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return path
    try:
        out = subprocess.run(
            ["fc-match", "-f", "%{file}", ":lang=ja:weight=bold"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        if out and Path(out).exists():
            return out
    except (OSError, subprocess.CalledProcessError):
        pass
    raise RuntimeError(
        "日本語フォントが見つかりません。fonts-noto-cjk をインストールするか "
        "YT_FONT_PATH を設定してください。"
    )


def _gradient() -> Image.Image:
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)
    for y in range(H):
        t = y / (H - 1)
        color = tuple(int(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM))
        draw.line([(0, y), (W, y)], fill=color)
    return img


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    """日本語向けに1文字単位で折り返す(明示的な改行は尊重)。"""
    lines: list[str] = []
    for para in text.split("\n"):
        cur = ""
        for ch in para:
            if draw.textlength(cur + ch, font=font) <= max_w:
                cur += ch
            else:
                lines.append(cur)
                cur = ch
        lines.append(cur)
    return lines


def _fit_text(draw, text: str, font_path: str, max_w: int, max_h: int, start: int):
    explicit = text.count("\n") + 1
    # まず折り返しなし(明示改行のみ)で収まるまで縮小し、それでも無理なら折り返しを許可
    for allow_wrap, floor in ((False, 64), (True, 30)):
        size = start
        while size > floor:
            font = ImageFont.truetype(font_path, size)
            lines = _wrap(draw, text, font, max_w)
            line_h = int(size * 1.45)
            if (allow_wrap or len(lines) == explicit) and line_h * len(lines) <= max_h:
                return font, lines, line_h
            size -= 4
    font = ImageFont.truetype(font_path, size)
    return font, _wrap(draw, text, font, max_w), int(size * 1.45)


def render_slide(slide: Slide, header: str, idx: int, total: int,
                 font_path: str, bg: Image.Image) -> Image.Image:
    img = bg.copy()
    draw = ImageDraw.Draw(img)

    # ヘッダー(角丸の帯)
    hfont = ImageFont.truetype(font_path, 54)
    hw = draw.textlength(header, font=hfont)
    pad = 36
    box = (W / 2 - hw / 2 - pad, 170, W / 2 + hw / 2 + pad, 170 + 100)
    draw.rounded_rectangle(box, radius=50, fill=ACCENT)
    draw.text((W / 2, 220), header, font=hfont, fill=BG_TOP, anchor="mm")

    # 本文
    color = {"hook": ACCENT, "answer": ANSWER}.get(slide.kind, TEXT)
    start = {"hook": 104, "answer": 120}.get(slide.kind, 88)
    font, lines, line_h = _fit_text(draw, slide.text, font_path, W - 160, 1150, start)
    y = H / 2 - line_h * len(lines) / 2 + line_h / 2
    for line in lines:
        draw.text((W / 2, y), line, font=font, fill=color, anchor="mm",
                  stroke_width=3, stroke_fill=(0, 0, 0))
        y += line_h

    # 進捗バー
    bar_y = H - 260
    draw.rounded_rectangle((120, bar_y, W - 120, bar_y + 14), radius=7, fill=(70, 70, 100))
    filled = 120 + (W - 240) * (idx + 1) / total
    draw.rounded_rectangle((120, bar_y, filled, bar_y + 14), radius=7, fill=ACCENT)

    ffont = ImageFont.truetype(font_path, 40)
    draw.text((W / 2, H - 180), "基数変換マスター", font=ffont, fill=MUTED, anchor="mm")
    return img


def render_video(ep: Episode, out_path: Path) -> Path:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg が見つかりません")
    font_path = find_font()
    bg = _gradient()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        concat = []
        for i, slide in enumerate(ep.slides):
            png = tmpdir / f"slide_{i:02d}.png"
            render_slide(slide, ep.header, i, len(ep.slides), font_path, bg).save(png)
            concat.append(f"file '{png}'\nduration {slide.seconds}")
        # concat demuxer は最後のファイルを再掲しないと最終 duration が無視される
        concat.append(f"file '{tmpdir / f'slide_{len(ep.slides) - 1:02d}.png'}'")
        list_file = tmpdir / "list.txt"
        list_file.write_text("\n".join(concat) + "\n", encoding="utf-8")

        total = sum(s.seconds for s in ep.slides)
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", str(list_file),
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-vf", f"fps={FPS},format=yuv420p",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-b:a", "128k",
            "-t", f"{total:.2f}", "-movflags", "+faststart",
            str(out_path),
        ]
        subprocess.run(cmd, check=True)
    return out_path


def render_preview(ep: Episode, out_dir: Path) -> list[Path]:
    """動画を作らずにスライド画像だけ書き出す(確認用)。"""
    font_path = find_font()
    bg = _gradient()
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, slide in enumerate(ep.slides):
        p = out_dir / f"slide_{i:02d}.png"
        render_slide(slide, ep.header, i, len(ep.slides), font_path, bg).save(p)
        paths.append(p)
    return paths
