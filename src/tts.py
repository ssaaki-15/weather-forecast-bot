"""
③ 音声合成モジュール（VOICEVOX）
- VOICEVOX Engine（無料・ローカル実行）を使用
- GitHub Actions では Docker サービスコンテナとして起動
- 商用利用時は各キャラクターのライセンスを必ず確認すること
"""

import json
import logging
import os
import time
import urllib.request
import urllib.error
from pathlib import Path

from config import VOICEVOX_CONFIG

logger = logging.getLogger(__name__)


class VoicevoxTTS:
    """VOICEVOX HTTP API クライアント"""

    def __init__(self, host: str | None = None, speaker_id: int | None = None):
        self.host = host or VOICEVOX_CONFIG["host"]
        self.speaker_id = speaker_id or VOICEVOX_CONFIG["speaker_id"]

    def _post_json(self, path: str, data: dict) -> bytes | None:
        """JSON POSTリクエストを送信"""
        url = f"{self.host}{path}"
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except urllib.error.URLError as e:
            logger.error(f"VOICEVOX request error: {e}")
            return None

    def _get_audio_query(self, text: str) -> dict | None:
        """テキストから音声クエリを生成"""
        url = (
            f"{self.host}/audio_query"
            f"?text={urllib.parse.quote(text)}"
            f"&speaker={self.speaker_id}"
        )
        req = urllib.request.Request(url, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.error(f"audio_query error: {e}")
            return None

    def _synthesize(self, audio_query: dict) -> bytes | None:
        """音声クエリから音声データを合成"""
        # パラメータ上書き
        audio_query.update({
            "speedScale":       VOICEVOX_CONFIG["speed_scale"],
            "pitchScale":       VOICEVOX_CONFIG["pitch_scale"],
            "volumeScale":      VOICEVOX_CONFIG["volume_scale"],
            "intonationScale":  VOICEVOX_CONFIG["intonation_scale"],
            "prePhonemeLength": VOICEVOX_CONFIG["pre_phoneme_length"],
            "postPhonemeLength":VOICEVOX_CONFIG["post_phoneme_length"],
        })
        return self._post_json(
            f"/synthesis?speaker={self.speaker_id}",
            audio_query,
        )

    def synthesize_to_file(self, text: str, output_path: str | Path) -> bool:
        """
        テキストを音声ファイルに変換して保存

        Args:
            text:        読み上げテキスト
            output_path: 保存先（.wavファイル）

        Returns:
            成功時 True
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # URLエンコードのためにimport
        import urllib.parse

        logger.info(f"音声合成: {len(text)}文字 → {output_path.name}")

        # Step1: audio_query
        query = self._get_audio_query(text)
        if not query:
            logger.error("audio_query の取得に失敗しました")
            return False

        # Step2: synthesis
        wav_data = self._synthesize(query)
        if not wav_data:
            logger.error("音声合成に失敗しました")
            return False

        output_path.write_bytes(wav_data)
        logger.info(f"音声ファイル保存: {output_path} ({len(wav_data):,} bytes)")
        return True

    def wait_until_ready(self, timeout_sec: int = 60, interval_sec: float = 2.0) -> bool:
        """VOICEVOXが起動するまで待機"""
        url = f"{self.host}/version"
        logger.info("VOICEVOX の起動待機中...")
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=5) as resp:
                    version = json.loads(resp.read().decode("utf-8"))
                    logger.info(f"VOICEVOX 起動確認 (version: {version})")
                    return True
            except Exception:
                time.sleep(interval_sec)
        logger.error(f"VOICEVOX が {timeout_sec}秒以内に起動しませんでした")
        return False


def split_text_for_tts(text: str, max_chars: int = 150) -> list[str]:
    """
    長文を句読点で分割してTTSに渡しやすくする
    VOICEVOX は長文を一度に処理すると不安定になる場合がある
    """
    chunks = []
    current = ""
    for char in text:
        current += char
        if char in ("。", "、", "！", "？", "\n") and len(current) >= max_chars:
            chunks.append(current.strip())
            current = ""
    if current.strip():
        chunks.append(current.strip())
    return chunks if chunks else [text]
