# YouTube 全自動投稿のセットアップ

GitHub Actions が **毎日 18:07 (日本時間)** に「究極の2択」ショート動画を自動で作って YouTube に投稿します。

- 1本に3問。ずんだもんと四国めたん（VOICEVOX）が別々の側を選んで理由を話し、最後に「コメントで 1A 2B 3A みたいに教えてね」と呼びかけます。
- BGM・効果音はコードで合成（著作権フリー）。説明欄に VOICEVOX のクレジットを自動で入れます。
- 2択のネタは `youtube_bot/choices.json`（1行 = `[A, Aの絵文字, Aの理由, B, Bの絵文字, Bの理由]`）。追加すると自動でローテーションに入ります。理由は「〜からなのだ」「〜からよ」が後ろにつく形で書いてください。

---

## 1. Google Cloud で YouTube API を有効にする（約10分・1回だけ）

1. https://console.cloud.google.com/ で新しいプロジェクトを作成
2. 「API とサービス」→「ライブラリ」→ **YouTube Data API v3** を有効化
3. 「OAuth 同意画面」を設定
   - User Type: **外部**
   - スコープに `.../auth/youtube.upload` を追加
   - テストユーザーに自分の Google アカウントを追加
   - 設定後、公開ステータスを **「本番環境に公開」** にする
     （「テスト」のままだとトークンが **7日で失効** して投稿が止まります）
4. 「認証情報」→「認証情報を作成」→ **OAuth クライアント ID** → 種類 **デスクトップアプリ**
   → JSON をダウンロード（`client_secret.json`）

## 2. リフレッシュトークンを取得する（自分のPCで1回だけ）

```bash
pip install google-auth-oauthlib
python scripts/get_refresh_token.py client_secret.json
```

ブラウザで **投稿先チャンネルの Google アカウント** でログインして許可します
（「このアプリは確認されていません」と出たら「詳細」→「移動」で進めてOK）。
表示された 3 つの値を控えます。`client_secret.json` はリポジトリに入れないでください。

## 3. GitHub Secrets に登録

リポジトリの **Settings → Secrets and variables → Actions → New repository secret**

| 名前 | 値 |
| --- | --- |
| `YT_CLIENT_ID` | 手順2で表示された値 |
| `YT_CLIENT_SECRET` | 手順2で表示された値 |
| `YT_REFRESH_TOKEN` | 手順2で表示された値 |

（任意）同じ画面の **Variables** タブで `YT_PRIVACY` を `private` / `unlisted` にすると、
公開前に確認できます。未設定なら `public`。

## 4. 動作確認

**Actions** タブ → 「YouTube 自動投稿」→ **Run workflow**

- `dry_run` にチェック → 動画だけ作成（Artifacts からダウンロードして確認できます）
- チェックなし → 実際に投稿

この workflow がデフォルトブランチ（main）にマージされると、毎日の自動実行が始まります。

---

## 注意点

- **未審査の API プロジェクトからの投稿は「非公開」に固定されます。**
  2020年7月以降に作られた API プロジェクトは、Google の監査
  （[YouTube API Services 監査フォーム](https://support.google.com/youtube/contact/yt_api_form)）
  を通過するまで、`public` を指定しても非公開になります。
  公開投稿するには監査を申請してください（数日〜数週間）。
- API の無料枠は 1日 10,000 ユニット、アップロードは 1本あたり約 1,600。1日1本なら余裕です。
- 公開リポジトリは 60日間コミットがないと定期実行が自動停止します。Actions タブから再有効化できます。
- 手元で試す場合: `pip install -r requirements-youtube.txt` と ffmpeg を入れて
  VOICEVOX エンジンを起動（`docker run -p 50021:50021 voicevox/voicevox_engine:cpu-latest`）してから
  `python -m youtube_bot --dry-run`（`output/` に mp4 ができます）。
