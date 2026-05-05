"""
⑥ YouTube アップロードモジュール
- YouTube Data API v3 を使用（無料枠で1本/日は十分）
- OAuth2 リフレッシュトークンを使用（GitHub Secrets で管理）
- 初回はローカルで setup_youtube_auth.py を実行してトークン取得
"""

import json
import logging
import os
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path

from config import YOUTUBE_CONFIG, WEEKDAY_JA

logger = logging.getLogger(__name__)
JST = timezone(timedelta(hours=9))

YOUTUBE_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
YOUTUBE_TOKEN_URL  = "https://oauth2.googleapis.com/token"
CHUNK_SIZE = 1024 * 1024 * 8  # 8MB チャンク


class YouTubeUploader:
    """YouTube Data API v3 アップローダー"""

    def __init__(self):
        self.client_id     = os.environ.get("YOUTUBE_CLIENT_ID", "")
        self.client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET", "")
        self.refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN", "")
        self._access_token: str | None = None

    def _refresh_access_token(self) -> str:
        """リフレッシュトークンでアクセストークンを取得"""
        body = urllib.parse.urlencode({
            "client_id":     self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
            "grant_type":    "refresh_token",
        }).encode("utf-8")

        req = urllib.request.Request(
            YOUTUBE_TOKEN_URL,
            data=body,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                token = data.get("access_token", "")
                if not token:
                    raise ValueError(f"アクセストークン取得失敗: {data}")
                logger.info("YouTube アクセストークン更新完了")
                return token
        except Exception as e:
            raise RuntimeError(f"トークン更新エラー: {e}")

    @property
    def access_token(self) -> str:
        if not self._access_token:
            self._access_token = self._refresh_access_token()
        return self._access_token

    def _build_metadata(self, dt: datetime, region_summary: str) -> dict:
        """動画メタデータを構築"""
        weekday = WEEKDAY_JA[dt.weekday()]
        date_str = dt.strftime(f"%Y年%m月%d日（{weekday}）")
        time_str = dt.strftime("%H:%M")

        title = YOUTUBE_CONFIG["title_template"].format(
            date=date_str, weekday=weekday, time=time_str
        )
        description = YOUTUBE_CONFIG["description_template"].format(
            date=date_str, weekday=weekday, region_summary=region_summary
        )
        return {
            "snippet": {
                "title":       title,
                "description": description,
                "tags":        YOUTUBE_CONFIG["tags"],
                "categoryId":  YOUTUBE_CONFIG["category_id"],
                "defaultLanguage": "ja",
            },
            "status": {
                "privacyStatus": YOUTUBE_CONFIG["privacy_status"],
                "selfDeclaredMadeForKids": False,
            },
        }

    def _initiate_resumable_upload(self, metadata: dict, file_size: int) -> str:
        """
        レジューム可能なアップロードセッションを開始
        YouTube推奨の大きなファイルアップロード方式
        """
        params = urllib.parse.urlencode({
            "uploadType": "resumable",
            "part": "snippet,status",
        })
        url = f"{YOUTUBE_UPLOAD_URL}?{params}"

        body = json.dumps(metadata).encode("utf-8")
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={
                "Authorization":           f"Bearer {self.access_token}",
                "Content-Type":            "application/json",
                "X-Upload-Content-Type":   "video/mp4",
                "X-Upload-Content-Length": str(file_size),
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            upload_url = resp.getheader("Location")
            if not upload_url:
                raise ValueError("アップロードURL取得失敗")
            logger.info(f"アップロードセッション開始: {upload_url[:80]}...")
            return upload_url

    def _upload_chunks(self, upload_url: str, video_path: Path) -> dict:
        """チャンク分割でファイルをアップロード"""
        file_size = video_path.stat().st_size
        uploaded = 0

        with open(video_path, "rb") as f:
            while uploaded < file_size:
                chunk = f.read(CHUNK_SIZE)
                chunk_end = min(uploaded + len(chunk) - 1, file_size - 1)
                content_range = f"bytes {uploaded}-{chunk_end}/{file_size}"

                req = urllib.request.Request(
                    upload_url, data=chunk, method="PUT",
                    headers={
                        "Content-Length": str(len(chunk)),
                        "Content-Range":  content_range,
                    },
                )
                try:
                    with urllib.request.urlopen(req, timeout=120) as resp:
                        if resp.status in (200, 201):
                            result = json.loads(resp.read().decode("utf-8"))
                            video_id = result.get("id", "")
                            logger.info(f"アップロード完了: video_id={video_id}")
                            return result
                except urllib.error.HTTPError as e:
                    if e.code == 308:  # Resume Incomplete
                        range_header = e.headers.get("Range", "")
                        if range_header:
                            uploaded = int(range_header.split("-")[1]) + 1
                        else:
                            uploaded += len(chunk)
                        pct = uploaded / file_size * 100
                        logger.debug(f"アップロード進捗: {pct:.1f}%")
                        continue
                    raise

                uploaded += len(chunk)

        raise RuntimeError("アップロードが完了しませんでした")

    def upload(self, video_path: Path, dt: datetime, region_summary: str) -> str:
        """
        動画をYouTubeにアップロード

        Args:
            video_path:     アップロードする動画ファイル
            dt:             放送日時
            region_summary: 概要欄用の地域別サマリー

        Returns:
            YouTube動画ID
        """
        if not video_path.exists():
            raise FileNotFoundError(f"動画ファイルが見つかりません: {video_path}")

        file_size = video_path.stat().st_size
        logger.info(f"YouTube アップロード開始: {video_path.name} ({file_size:,} bytes)")

        metadata = self._build_metadata(dt, region_summary)
        upload_url = self._initiate_resumable_upload(metadata, file_size)
        result = self._upload_chunks(upload_url, video_path)

        video_id = result.get("id", "")
        if video_id:
            yt_url = f"https://www.youtube.com/watch?v={video_id}"
            logger.info(f"✅ YouTube アップロード完了: {yt_url}")
        return video_id

    def add_to_playlist(self, video_id: str, playlist_id: str) -> bool:
        """動画をプレイリストに追加"""
        if not playlist_id:
            return False
        url = "https://www.googleapis.com/youtube/v3/playlistItems?part=snippet"
        body = json.dumps({
            "snippet": {
                "playlistId": playlist_id,
                "resourceId": {
                    "kind":    "youtube#video",
                    "videoId": video_id,
                },
            }
        }).encode("utf-8")
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type":  "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30):
                logger.info(f"プレイリスト追加完了: {playlist_id}")
                return True
        except Exception as e:
            logger.warning(f"プレイリスト追加失敗（致命的ではありません）: {e}")
            return False


def build_region_summary(regions: list[dict]) -> str:
    """YouTube概要欄用の地域サマリーテキストを生成"""
    lines = []
    for r in regions:
        td = r.get("today", {})
        lines.append(
            f"・{r['name']}：{td.get('weather','--')} "
            f"（最高{td.get('temp_max','--')}℃ / 最低{td.get('temp_min','--')}℃）"
        )
    return "\n".join(lines)
