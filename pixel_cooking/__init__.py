"""ドット絵の料理当てクイズ動画ジェネレーター。"""

from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image

from . import gfx
from .audio import build_audio, write_wav
from .dishes import BY_KEY, DISHES
from .engine import DURATION, THEMES, Scene

__all__ = ["DISHES", "BY_KEY", "THEMES", "Scene", "make_video", "pick"]


def pick(index: int):
    """index 本目の動画に使う (料理, テーマ)。料理が一周するごとにテーマを変える。"""
    dish = DISHES[index % len(DISHES)]
    theme = THEMES[(index // len(DISHES)) % len(THEMES)]
    return dish, theme


def make_video(dish, theme, out_path, seed: int = 0) -> Path:
    sc = Scene(dish, theme, seed)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    wav = out.with_suffix(".wav")
    write_wav(wav, build_audio(sc))
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{gfx.W}x{gfx.H}", "-r", str(gfx.FPS), "-i", "-",
           "-i", str(wav),
           "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p", "-tune", "animation",
           "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
           "-shortest", "-movflags", "+faststart", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for f in range(int(DURATION * gfx.FPS)):
        frame = sc.render(f / gfx.FPS).resize((gfx.W, gfx.H), Image.NEAREST)
        proc.stdin.write(frame.tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg の書き出しに失敗しました")
    wav.unlink()
    return out
