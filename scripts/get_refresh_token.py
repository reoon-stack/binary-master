"""YouTube 用のリフレッシュトークンを取得する(自分のPCで1回だけ実行)。

  pip install google-auth-oauthlib
  python scripts/get_refresh_token.py client_secret.json

ブラウザが開くので、動画を投稿したい YouTube チャンネルの Google アカウントでログインして許可。
表示された3つの値を GitHub Secrets に登録します。
"""

import json
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("使い方: python scripts/get_refresh_token.py client_secret.json")
    path = sys.argv[1]
    flow = InstalledAppFlow.from_client_secrets_file(path, SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
    info = json.load(open(path, encoding="utf-8"))
    client = info.get("installed") or info.get("web")
    print("\n以下を GitHub の Settings > Secrets and variables > Actions に登録してください:\n")
    print(f"YT_CLIENT_ID     = {client['client_id']}")
    print(f"YT_CLIENT_SECRET = {client['client_secret']}")
    print(f"YT_REFRESH_TOKEN = {creds.refresh_token}")


if __name__ == "__main__":
    main()
