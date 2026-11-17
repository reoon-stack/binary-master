"""使い方:
  python -m pixel_cooking --dish curry out.mp4
  python -m pixel_cooking --dish curry --preview 4 12 28 outdir/   # 静止画で確認
  python -m pixel_cooking --list
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

from . import BY_KEY, DISHES, THEMES, Scene, gfx, make_video


def main():
    p = argparse.ArgumentParser()
    p.add_argument("out", nargs="?", default="output/dish.mp4")
    p.add_argument("--dish", default=DISHES[0].key, choices=list(BY_KEY))
    p.add_argument("--theme", type=int, default=0)
    p.add_argument("--preview", type=float, nargs="*")
    p.add_argument("--list", action="store_true")
    a = p.parse_args()
    if a.list:
        for d in DISHES:
            print(f"{d.key:12s} {d.answer}")
        return
    dish, theme = BY_KEY[a.dish], THEMES[a.theme % len(THEMES)]
    if a.preview:
        sc = Scene(dish, theme)
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        for t in a.preview:
            sc.render(t).resize((gfx.W, gfx.H), Image.NEAREST).save(out / f"{dish.key}_{t:05.2f}.png")
        return
    print(make_video(dish, theme, a.out))


if __name__ == "__main__":
    main()
