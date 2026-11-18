"""YouTube Data API v3 で動画をアップロードする。

必要な環境変数 (GitHub Secrets に登録):
  YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from .meta import Episode

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CATEGORY_HOWTO = "26"  # ハウツーとスタイル(料理)


def _credentials():
    from google.oauth2.credentials import Credentials

    missing = [k for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN")
               if not os.environ.get(k)]
    if missing:
        raise RuntimeError(
            f"環境変数が未設定です: {', '.join(missing)}\n"
            "YOUTUBE_SETUP.md の手順で GitHub Secrets に登録してください。"
        )
    return Credentials(
        token=None,
        refresh_token=os.environ["YT_REFRESH_TOKEN"],
        client_id=os.environ["YT_CLIENT_ID"],
        client_secret=os.environ["YT_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )


def clean_tags(tags):
    """YouTube が受け付けるタグだけにする(記号を除き、合計 400 文字以内)。"""
    out, total = [], 0
    for t in tags:
        t = "".join(ch for ch in t if ch not in '<>,"#&').strip()
        if not t or len(t) > 30 or t in out:
            continue
        cost = len(t) + (2 if " " in t else 0) + 1
        if total + cost > 400:
            break
        out.append(t)
        total += cost
    return out


def upload(ep: Episode, video: Path, privacy: str = "public") -> str:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    youtube = build("youtube", "v3", credentials=_credentials(), cache_discovery=False)

    def body_for(minimal: bool):
        snippet = {
            "title": ep.title,
            "description": ep.description[:5000],
            "categoryId": CATEGORY_HOWTO,
            "defaultLanguage": "ja",
            "defaultAudioLanguage": "ja",
        }
        if not minimal:
            snippet["tags"] = clean_tags(ep.tags)
        return {"snippet": snippet,
                "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False}}

    def send(body):
        media = MediaFileUpload(str(video), mimetype="video/mp4", chunksize=-1, resumable=True)
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
        response = None
        for attempt in range(5):
            try:
                while response is None:
                    _, response = request.next_chunk()
                return response
            except HttpError as e:
                if e.resp.status not in (500, 502, 503, 504) or attempt == 4:
                    raise
                time.sleep(2 ** attempt * 5)

    try:
        response = send(body_for(minimal=False))
    except HttpError as e:
        # タグなどの付加情報が原因で断られたら、最小限の情報でもう一度送る(投稿を優先)
        if e.resp.status == 400 and b"INVALID_REQUEST_METADATA" in (e.content or b""):
            print("タグなどの情報で断られたので、タグなしで送り直します:", e)
            response = send(body_for(minimal=True))
        else:
            raise

    video_id = response["id"]
    return video_id
