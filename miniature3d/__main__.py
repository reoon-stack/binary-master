import argparse
import time
from pathlib import Path

from .scene import Scene, make_video


def main():
    p = argparse.ArgumentParser()
    p.add_argument("out", nargs="?", default="output/room.mp4")
    p.add_argument("--preview", type=float, nargs="*")
    a = p.parse_args()
    if a.preview:
        sc = Scene()
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        for t in a.preview:
            t0 = time.time()
            sc.render(t).save(out / f"room_{t:05.2f}.png")
            print(f"{t:5.2f}s  {time.time() - t0:.2f}s/frame")
        return
    print(make_video(a.out))


if __name__ == "__main__":
    main()
