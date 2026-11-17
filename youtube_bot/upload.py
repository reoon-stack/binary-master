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


def upload(ep: Episode, video: Path, privacy: str = "public") -> str:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    youtube = build("youtube", "v3", credentials=_credentials(), cache_discovery=False)
    body = {
        "snippet": {
            "title": ep.title,
            "description": ep.description[:5000],
            "tags": ep.tags,
            "categoryId": CATEGORY_HOWTO,
            "defaultLanguage": "ja",
            "defaultAudioLanguage": "zxx",
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(str(video), mimetype="video/mp4", chunksize=-1, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    for attempt in range(5):
        try:
            while response is None:
                _, response = request.next_chunk()
            break
        except HttpError as e:
            if e.resp.status not in (500, 502, 503, 504) or attempt == 4:
                raise
            time.sleep(2 ** attempt * 5)

    video_id = response["id"]
    return video_id
