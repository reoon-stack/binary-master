"""ドット絵の料理当てクイズ動画を作って YouTube に投稿する。

  python -m youtube_bot                 # 今日の動画を作ってアップロード
  python -m youtube_bot --dry-run       # 動画を作るだけ(アップロードしない)
  python -m youtube_bot --index 3 --dry-run
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from pixel_cooking import DISHES, make_video, pick

from .meta import build_episode


def day_number(date: dt.date) -> int:
    return (date - dt.date(2026, 1, 1)).days


def main() -> None:
    p = argparse.ArgumentParser(description="YouTube Shorts 自動投稿(ドット絵料理)")
    p.add_argument("--date", help="YYYY-MM-DD (既定: 今日・日本時間)")
    p.add_argument("--index", type=int, help="何本目の動画か (既定: 日付で自動)")
    p.add_argument("--out", default="output", help="出力フォルダ")
    p.add_argument("--dry-run", action="store_true", help="アップロードしない")
    p.add_argument("--privacy", default=os.environ.get("YT_PRIVACY", "public"),
                   choices=["public", "unlisted", "private"])
    args = p.parse_args()

    date = (dt.date.fromisoformat(args.date) if args.date
            else dt.datetime.now(ZoneInfo("Asia/Tokyo")).date())
    index = args.index if args.index is not None else day_number(date)
    dish, theme = pick(index)
    ep = build_episode(dish, index)
    print(f"[{date}] #{index} {dish.key}({dish.answer}) / テーマ {index // len(DISHES)} : {ep.title}")

    video = make_video(dish, theme, Path(args.out) / f"{date}_{dish.key}.mp4", seed=index)
    print(f"動画を作成しました: {video}")
    if args.dry_run:
        return

    from .upload import upload

    video_id = upload(ep, video, args.privacy)
    print(f"アップロード完了 ({args.privacy}): https://youtube.com/shorts/{video_id}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"### {ep.title}\n答え: {dish.answer}\nhttps://youtube.com/shorts/{video_id} ({args.privacy})\n")


if __name__ == "__main__":
    main()
