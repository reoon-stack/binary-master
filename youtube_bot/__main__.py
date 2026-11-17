"""使い方:
  python -m youtube_bot                 # 今日の動画を作ってアップロード
  python -m youtube_bot --dry-run       # 動画を作るだけ(アップロードしない)
  python -m youtube_bot --kind quiz --dry-run
  python -m youtube_bot --kind tip --index 3 --preview   # スライド画像だけ確認
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from .content import episode_for
from .render import render_preview, render_video


def main() -> None:
    p = argparse.ArgumentParser(description="YouTube Shorts 自動投稿")
    p.add_argument("--date", help="YYYY-MM-DD (既定: 今日・日本時間)")
    p.add_argument("--kind", choices=["tip", "quiz"], help="既定: 日付で自動選択")
    p.add_argument("--index", type=int, help="豆知識の番号 / クイズのシード")
    p.add_argument("--out", default="output", help="出力フォルダ")
    p.add_argument("--dry-run", action="store_true", help="アップロードしない")
    p.add_argument("--preview", action="store_true", help="スライド画像だけ出力")
    p.add_argument("--privacy", default=os.environ.get("YT_PRIVACY", "public"),
                   choices=["public", "unlisted", "private"])
    args = p.parse_args()

    date = (dt.date.fromisoformat(args.date) if args.date
            else dt.datetime.now(ZoneInfo("Asia/Tokyo")).date())
    ep = episode_for(date, args.kind, args.index)
    out = Path(args.out)
    print(f"[{date}] {ep.kind}: {ep.title}")

    if args.preview:
        for path in render_preview(ep, out / "preview"):
            print(path)
        return

    video = render_video(ep, out / f"{date}_{ep.kind}.mp4")
    print(f"動画を作成しました: {video}")
    if args.dry_run:
        return

    from .upload import upload

    video_id = upload(ep, video, args.privacy)
    print(f"アップロード完了 ({args.privacy}): https://youtube.com/shorts/{video_id}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"### {ep.title}\nhttps://youtube.com/shorts/{video_id} ({args.privacy})\n")


if __name__ == "__main__":
    main()
