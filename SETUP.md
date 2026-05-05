# 🌤 天気予報自動配信システム セットアップガイド

## 概要

毎朝7時に気象庁データから天気予報動画を自動生成し、YouTubeに投稿するシステムです。

```
気象庁API → Claude Haiku（原稿） → VOICEVOX（音声） → Pillow+FFmpeg（動画） → YouTube
```

**コスト試算（月額）**

| 項目 | 内容 | コスト |
|------|------|--------|
| Claude Haiku | 1回/日 × 30日、約700トークン/回 | 約 **$0.10/月** |
| VOICEVOX | Docker実行（GitHub Actions） | **無料** |
| GitHub Actions | 約30分/日（無料枠2000分/月以内） | **無料** |
| YouTube API | 1アップロード/日（無料枠内） | **無料** |
| 気象庁API | 公開エンドポイント | **無料** |
| **合計** | | **約 $0.10/月（≒15円/月）** |

---

## 手順1：リポジトリの準備

```bash
# GitHubに新規リポジトリを作成してpush
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/weather-forecast-bot.git
git push -u origin main
```

---

## 手順2：Anthropic APIキーの取得

1. [https://console.anthropic.com](https://console.anthropic.com) にアクセス
2. API Keys → Create Key
3. 生成されたキーをコピー（次のステップで使用）

---

## 手順3：YouTube Data API の設定

### 3-1. Google Cloud プロジェクト作成

1. [Google Cloud Console](https://console.cloud.google.com) にアクセス
2. 新規プロジェクト作成（例: `weather-forecast-bot`）
3. 左メニュー「APIとサービス」→「ライブラリ」
4. **YouTube Data API v3** を検索して「有効にする」

### 3-2. OAuth2 クライアントID 作成

1. 「APIとサービス」→「認証情報」→「認証情報を作成」
2. **OAuth クライアント ID** を選択
3. アプリケーションの種類: **デスクトップアプリ**
4. 名前: 任意（例: `weather-bot`）
5. 作成後、**クライアントID** と **クライアントシークレット** をメモ

### 3-3. OAuth 同意画面の設定

1. 「OAuth 同意画面」→ ユーザーの種類: **外部**
2. アプリ名・メールアドレスを入力
3. スコープ: `youtube.upload`, `youtube` を追加
4. テストユーザー: 自分のGoogleアカウントを追加

### 3-4. リフレッシュトークン取得（ローカルで1回だけ実行）

```bash
# 依存パッケージをインストール
pip install -r requirements.txt

# セットアップスクリプトを実行
# scripts/setup_youtube_auth.py の CLIENT_ID と CLIENT_SECRET を先に編集すること
python scripts/setup_youtube_auth.py
```

ブラウザが開くので YouTube アカウントで認可 → ターミナルに **リフレッシュトークン** が表示される

---

## 手順4：GitHub Secrets の登録

GitHub リポジトリの **Settings → Secrets and variables → Actions** に以下を登録：

| シークレット名 | 値 |
|--------------|-----|
| `ANTHROPIC_API_KEY` | Anthropic APIキー |
| `YOUTUBE_CLIENT_ID` | Google OAuth2 クライアントID |
| `YOUTUBE_CLIENT_SECRET` | Google OAuth2 クライアントシークレット |
| `YOUTUBE_REFRESH_TOKEN` | setup_youtube_auth.py で取得したトークン |

---

## 手順5：BGMの配置（任意）

著作権フリーのBGMを `assets/bgm.mp3` として配置してください。
推奨サイト: [DOVA-SYNDROME](https://dova-s.jp)（無料・商用利用可）

BGMがない場合はそのまま動作します（ナレーションのみ）。

---

## 手順6：動作確認

```bash
# ローカルでテスト実行（VOICEVOX を別途起動しておく）
# Dockerがある場合:
docker run --rm -p 50021:50021 voicevox/voicevox_engine:cpu-ubuntu20.04-latest &

# 環境変数を設定
cp .env.example .env
# .env を編集して実際の値を入力

# 実行
python main.py
```

---

## 手順7：自動実行の有効化

GitHub Actions はデフォルトで有効です。
`Settings → Actions → General` で Actions が有効になっていることを確認してください。

**スケジュール**: 毎日 22:00 UTC（= 翌日 07:00 JST）

手動実行: `Actions → 🌤 天気予報自動配信 → Run workflow`

---

## カスタマイズ

### 配信地域を変更する（`config.py`）

```python
JMA_REGIONS = [
    {"key": "kanto", "name": "関東", "code": "130000", ...},
    # 必要な地域だけ残す
]
```

### キャラクターボイスを変更する（`config.py`）

```python
VOICEVOX_CONFIG = {
    "speaker_id": 8,  # 春日部つむぎ / 他のキャラIDはconfig.pyのVOICEVOX_SPEAKERS参照
    ...
}
```

### 動画スタイルを変更する（`config.py`）

```python
COLORS = {
    "bg_primary": "#1a1a2e",  # 背景色を変更
    ...
}
```

---

## トラブルシューティング

| 症状 | 原因 | 対処 |
|------|------|------|
| `VOICEVOX に接続できません` | Dockerが起動していない | `docker run ...` でVOICEVOX起動 |
| `Claude API エラー` | APIキーが無効 | Anthropic Consoleでキーを確認 |
| `YouTube アップロードエラー` | トークン期限切れ | `setup_youtube_auth.py` を再実行 |
| 文字化け | フォント未インストール | `sudo apt install fonts-noto-cjk` |
| 動画が生成されない | FFmpegがない | `sudo apt install ffmpeg` または `brew install ffmpeg` |

---

## ライセンス・利用規約

- **気象庁データ**: 出典明記で利用可（商用利用可）
- **VOICEVOX**: 各キャラクターの利用規約を必ず確認すること
- **BGM**: 使用素材のライセンスを個別に確認すること
- **YouTube**: YouTube利用規約に従うこと
