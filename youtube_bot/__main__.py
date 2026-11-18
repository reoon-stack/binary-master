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


# この日に 1 本目(DISHES[0])を投稿し、以降 1 日 1 品。全部投稿したら何もしない。
START_DATE = dt.date(2026, 11, 18)


def day_number(date: dt.date) -> int:
    return (date - START_DATE).days


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
    picked = pick(index)
    if picked is None:
        msg = (f"[{date}] #{index}: 投稿する料理がありません(全 {len(DISHES)} 品は投稿済み、"
               "または開始日前)。今日はスキップします。")
        print(msg)
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a", encoding="utf-8") as f:
                f.write(msg + "\n")
        return
    dish, theme = picked
    prev = pick(index - 1)
    ep = build_episode(dish, index, prev[0] if prev else None)
    print(f"[{date}] #{index + 1}/{len(DISHES)} {dish.key}({dish.answer}) : {ep.title}")

    video = make_video(dish, theme, Path(args.out) / f"{date}_{dish.key}.mp4", seed=index)
    print(f"動画を作成しました: {video}")
    if args.dry_run:
        return

    from .upload import upload

    video_id = upload(ep, video, args.privacy)
    print(f"アップロード完了 ({args.privacy}): https://youtube.com/shorts/{video_id}")
    # 予備の定期実行が同じ日に二重投稿しないための目印(ワークフローが artifact として残す)
    (Path(args.out) / "posted.txt").write_text(f"{date} {dish.key} {video_id}\n", encoding="utf-8")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"### {ep.title}\n答え: {dish.answer}\nhttps://youtube.com/shorts/{video_id} ({args.privacy})\n")


if __name__ == "__main__":
    main()
