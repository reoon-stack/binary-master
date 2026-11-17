"""使い方:
  python -m youtube_bot                 # 今日の動画を作ってアップロード
  python -m youtube_bot --dry-run       # 動画を作るだけ(アップロードしない)
  python -m youtube_bot --index 3 --dry-run

読み上げには VOICEVOX エンジン (http://127.0.0.1:50021) が必要。
手元で VOICEVOX なしに見た目だけ確認するときは --no-voice。
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

from . import audio
from .content import SPEAKERS, day_number, episode_for
from .render import render_video


def main() -> None:
    p = argparse.ArgumentParser(description="YouTube Shorts 自動投稿")
    p.add_argument("--date", help="YYYY-MM-DD (既定: 今日・日本時間)")
    p.add_argument("--index", type=int, help="台本の番号 (既定: 日付で自動)")
    p.add_argument("--out", default="output", help="出力フォルダ")
    p.add_argument("--dry-run", action="store_true", help="アップロードしない")
    p.add_argument("--no-voice", action="store_true", help="読み上げなしで作る(確認用)")
    p.add_argument("--privacy", default=os.environ.get("YT_PRIVACY", "public"),
                   choices=["public", "unlisted", "private"])
    args = p.parse_args()

    date = (dt.date.fromisoformat(args.date) if args.date
            else dt.datetime.now(ZoneInfo("Asia/Tokyo")).date())
    seed = args.index if args.index is not None else day_number(date)
    ep = episode_for(date, args.index)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    print(f"[{date}] {ep.title}")

    if args.no_voice:
        voices = [audio.placeholder_voice(l.text) for l in ep.lines]
    else:
        if not audio.voicevox_available():
            raise SystemExit(f"VOICEVOX エンジンに接続できません: {audio.VOICEVOX_URL}")
        voices = [audio.synthesize(l.text, SPEAKERS[l.speaker]["voicevox_id"])
                  for l in ep.lines]

    mixed, segments, total = audio.mix(voices, gap=0.25, tail=0.8, seed=seed)
    voice_only = np.zeros(int(audio.SR * total), dtype=np.float32)
    for v, s in zip(voices, segments):
        i = int(s.start * audio.SR)
        voice_only[i:i + v.size] = v[: voice_only.size - i]
    wav = out / "audio.wav"
    audio.write_wav(wav, mixed)

    video = render_video(ep, voice_only, wav, segments, total,
                         out / f"{date}.mp4", seed=seed)
    print(f"動画を作成しました: {video} ({total:.1f}秒)")
    if args.dry_run or args.no_voice:
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
