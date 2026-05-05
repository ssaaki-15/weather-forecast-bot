"""
🌤 天気予報自動配信システム - メインオーケストレーター
========================================================
実行フロー：
  ① 気象庁API  →  気象データ取得
  ② Claude API →  NHKスタイル原稿生成
  ③ VOICEVOX  →  音声合成
  ④ Pillow    →  フレーム画像生成
  ⑤ FFmpeg    →  動画合成（横型 + Shorts縦型）
  ⑥ YouTube API → アップロード・公開

実行条件：
  - 毎朝 7:00 JST（GitHub Actions cron: '0 22 * * *'）
  - 手動実行も可能（workflow_dispatch）

必要な環境変数（GitHub Secrets）：
  ANTHROPIC_API_KEY      … Claude API キー
  YOUTUBE_CLIENT_ID      … YouTube OAuth2 クライアントID
  YOUTUBE_CLIENT_SECRET  … YouTube OAuth2 クライアントシークレット
  YOUTUBE_REFRESH_TOKEN  … YouTube OAuth2 リフレッシュトークン
"""

import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ---- ログ設定 ----
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("weather_bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("main")

# ---- ローカルモジュール ----
from src.jma_fetcher import (
    fetch_national_overview,
    fetch_all_regions,
    format_region_data_for_prompt,
    format_warnings_for_prompt,
)
from src.script_generator import generate_script
from src.tts import VoicevoxTTS
from src.frame_generator import (
    generate_title_frame,
    generate_region_frame,
    generate_outro_frame,
)
from src.video_composer import compose_full_video, generate_srt
from src.youtube_uploader import YouTubeUploader, build_region_summary

JST = timezone(timedelta(hours=9))

# ---- パス設定 ----
BASE_DIR   = Path(__file__).parent
ASSETS_DIR = BASE_DIR / "assets"
OUTPUT_DIR = BASE_DIR / "output"


def main():
    now = datetime.now(JST)
    date_str = now.strftime("%Y%m%d")
    logger.info(f"{'='*60}")
    logger.info(f"🌤 天気予報システム 起動 — {now.strftime('%Y/%m/%d %H:%M JST')}")
    logger.info(f"{'='*60}")

    work_dir   = OUTPUT_DIR / date_str
    frames_dir = work_dir / "frames"
    audio_dir  = work_dir / "audio"
    work_dir.mkdir(parents=True, exist_ok=True)
    frames_dir.mkdir(exist_ok=True)
    audio_dir.mkdir(exist_ok=True)

    # ================================================================
    # ① 気象庁 データ取得
    # ================================================================
    logger.info("① 気象庁 API データ取得開始")
    try:
        national_overview = fetch_national_overview()
        regions = fetch_all_regions()
        logger.info(f"   取得完了: {len(regions)} 地域")
    except Exception as e:
        logger.error(f"気象データ取得エラー: {e}", exc_info=True)
        sys.exit(1)

    # ================================================================
    # ② 原稿生成（Claude API）
    # ================================================================
    logger.info("② Claude API 原稿生成開始")
    try:
        region_data_str = format_region_data_for_prompt(regions)
        warnings_str    = format_warnings_for_prompt(regions)

        script = generate_script(
            national_overview=national_overview,
            region_data_str=region_data_str,
            warnings_str=warnings_str,
            target_datetime=now,
        )
        # 原稿を保存
        script_path = work_dir / "script.txt"
        script_path.write_text(script, encoding="utf-8")
        logger.info(f"   原稿保存: {script_path}")
    except Exception as e:
        logger.error(f"原稿生成エラー: {e}", exc_info=True)
        sys.exit(1)

    # ================================================================
    # ③ 音声合成（VOICEVOX）
    # ================================================================
    logger.info("③ VOICEVOX 音声合成開始")
    tts = VoicevoxTTS()

    # VOICEVOX の起動確認（Docker起動直後は少し待つ）
    if not tts.wait_until_ready(timeout_sec=120):
        logger.error("VOICEVOXに接続できません。処理を中断します。")
        sys.exit(1)

    # 全体ナレーション（1ファイルにまとめる）
    main_audio_path = audio_dir / "narration_full.wav"
    tts_success = tts.synthesize_to_file(script, main_audio_path)
    if not tts_success:
        logger.warning("音声合成に失敗しました。音声なしで続行します。")
        main_audio_path = None

    # ================================================================
    # ④ フレーム生成（Pillow）
    # ================================================================
    logger.info("④ フレーム生成開始")

    title_path = frames_dir / "00_title.png"
    generate_title_frame(now, title_path)

    region_frames = []
    for i, region in enumerate(regions):
        frame_path = frames_dir / f"{i+1:02d}_{region['key']}.png"
        generate_region_frame(region, now, frame_path)
        region_frames.append((frame_path, None))  # 音声は全体1本を使用

    # 警報サマリー（エンディング用）
    all_warnings = []
    for r in regions:
        for w in r.get("warnings", []):
            all_warnings.append(f"{r['name']} {w['area']}：{w['type']}")

    outro_path = frames_dir / "99_outro.png"
    generate_outro_frame(now, all_warnings[:6], outro_path)

    logger.info(f"   フレーム生成完了: {len(region_frames)+2} 枚")

    # ================================================================
    # ⑤ 動画合成（FFmpeg）
    # ================================================================
    logger.info("⑤ 動画合成開始（FFmpeg）")

    # SRT字幕生成
    srt_content = generate_srt(script, regions, main_audio_path)
    srt_path = work_dir / "subtitles.srt"
    if srt_content:
        srt_path.write_text(srt_content, encoding="utf-8")
    else:
        srt_path = None

    bgm_path = ASSETS_DIR / "bgm.mp3"

    video_paths = compose_full_video(
        title_image=title_path,
        region_images=region_frames,
        outro_image=outro_path,
        audio_main=main_audio_path,
        bgm_path=bgm_path if bgm_path.exists() else None,
        srt_path=srt_path,
        output_dir=work_dir,
        date_str=date_str,
    )

    if not video_paths.get("horizontal"):
        logger.error("動画合成に失敗しました。")
        sys.exit(1)

    logger.info(f"   横型動画: {video_paths['horizontal']}")
    if video_paths.get("shorts"):
        logger.info(f"   縦型Shorts: {video_paths['shorts']}")

    # ================================================================
    # ⑥ YouTube アップロード
    # ================================================================
    logger.info("⑥ YouTube アップロード開始")

    # 認証情報チェック
    if not all([
        os.environ.get("YOUTUBE_CLIENT_ID"),
        os.environ.get("YOUTUBE_CLIENT_SECRET"),
        os.environ.get("YOUTUBE_REFRESH_TOKEN"),
    ]):
        logger.warning("YouTube 認証情報が設定されていません。アップロードをスキップします。")
        logger.info("   動画ファイルはローカルに保存されています:")
        logger.info(f"   → {video_paths['horizontal']}")
    else:
        try:
            uploader = YouTubeUploader()
            region_summary = build_region_summary(regions)

            # 横型動画をアップロード
            video_id = uploader.upload(
                video_path=video_paths["horizontal"],
                dt=now,
                region_summary=region_summary,
            )

            # プレイリスト追加（設定されている場合）
            from config import YOUTUBE_CONFIG
            if YOUTUBE_CONFIG.get("playlist_id") and video_id:
                uploader.add_to_playlist(video_id, YOUTUBE_CONFIG["playlist_id"])

            logger.info(f"✅ アップロード完了: https://www.youtube.com/watch?v={video_id}")

        except Exception as e:
            logger.error(f"YouTube アップロードエラー: {e}", exc_info=True)
            # アップロード失敗は致命的ではない（ローカルに動画は残る）

    # ================================================================
    # 完了サマリー
    # ================================================================
    logger.info(f"{'='*60}")
    logger.info("🎉 天気予報動画生成 完了！")
    logger.info(f"   日付:     {now.strftime('%Y/%m/%d %H:%M JST')}")
    logger.info(f"   地域数:   {len(regions)}")
    logger.info(f"   原稿文字: {len(script)}文字")
    logger.info(f"   警報数:   {len(all_warnings)}件")
    logger.info(f"   出力先:   {work_dir}")
    logger.info(f"{'='*60}")


if __name__ == "__main__":
    main()
