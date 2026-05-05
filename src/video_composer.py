"""
⑤ 動画合成モジュール（FFmpeg）
- 静止フレーム画像 + 音声 → MP4動画
- BGM合成・字幕焼き込み・縦型Shorts版同時生成
- FFmpegは GitHub Actions Ubuntu に標準インストール済み
"""

import logging
import os
import subprocess
import tempfile
from pathlib import Path

from config import VIDEO_CONFIG

logger = logging.getLogger(__name__)

W = VIDEO_CONFIG["width"]
H = VIDEO_CONFIG["height"]
FPS = VIDEO_CONFIG["fps"]
BGM_VOL = VIDEO_CONFIG["bgm_volume"]


def _run_ffmpeg(args: list[str], description: str = "") -> bool:
    """FFmpegコマンドを実行"""
    cmd = ["ffmpeg", "-y", "-loglevel", "warning"] + args
    logger.info(f"FFmpeg: {description or ' '.join(cmd[:6])}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            logger.error(f"FFmpeg エラー:\n{result.stderr}")
            return False
        return True
    except subprocess.TimeoutExpired:
        logger.error("FFmpeg がタイムアウトしました（300秒）")
        return False
    except FileNotFoundError:
        logger.error("FFmpegが見つかりません。インストールを確認してください。")
        return False


def image_to_video_clip(image_path: Path, duration_sec: float,
                          audio_path: Path | None, output_path: Path) -> bool:
    """
    静止画像 + 音声 → 一定時間の動画クリップを生成

    音声がある場合は音声の長さに合わせる（duration_sec は最小値）
    """
    if audio_path and audio_path.exists():
        # 音声の長さを取得
        probe_cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(audio_path)
        ]
        try:
            result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=30)
            audio_dur = float(result.stdout.strip())
            duration_sec = max(duration_sec, audio_dur)
        except Exception:
            pass

        args = [
            "-loop", "1", "-i", str(image_path),
            "-i", str(audio_path),
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "aac", "-b:a", "192k",
            "-t", str(duration_sec),
            "-pix_fmt", "yuv420p",
            "-shortest",
            str(output_path),
        ]
    else:
        args = [
            "-loop", "1", "-i", str(image_path),
            "-c:v", "libx264", "-preset", "fast",
            "-t", str(duration_sec),
            "-pix_fmt", "yuv420p",
            "-an",
            str(output_path),
        ]

    return _run_ffmpeg(args, f"画像→動画: {image_path.name}")


def concatenate_clips(clip_paths: list[Path], output_path: Path) -> bool:
    """複数の動画クリップを連結"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                     delete=False, encoding="utf-8") as f:
        for p in clip_paths:
            f.write(f"file '{p.resolve()}'\n")
        concat_list = f.name

    args = [
        "-f", "concat", "-safe", "0",
        "-i", concat_list,
        "-c", "copy",
        str(output_path),
    ]
    success = _run_ffmpeg(args, f"クリップ連結 ({len(clip_paths)}本)")
    os.unlink(concat_list)
    return success


def add_bgm(video_path: Path, bgm_path: Path, output_path: Path,
             bgm_volume: float = BGM_VOL) -> bool:
    """
    動画にBGMを混合
    - BGMは動画の長さにループして合わせる
    - 既存の音声（ナレーション）はそのまま保持
    """
    if not bgm_path.exists():
        logger.warning(f"BGMファイルが見つかりません: {bgm_path}。BGMなしで続行。")
        import shutil
        shutil.copy(video_path, output_path)
        return True

    args = [
        "-i", str(video_path),
        "-stream_loop", "-1", "-i", str(bgm_path),
        "-filter_complex",
        (
            f"[1:a]volume={bgm_volume},aloop=loop=-1:size=2e+09[bgm];"
            f"[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=3[a]"
        ),
        "-map", "0:v",
        "-map", "[a]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(output_path),
    ]
    return _run_ffmpeg(args, "BGM合成")


def burn_subtitles(video_path: Path, srt_path: Path, output_path: Path) -> bool:
    """SRT字幕ファイルを動画に焼き込み"""
    if not srt_path.exists():
        logger.warning("字幕ファイルが見つかりません。字幕なしで続行。")
        import shutil
        shutil.copy(video_path, output_path)
        return True

    # フォントの指定（Noto Sans CJK を使用）
    font_name = "Noto Sans CJK JP"
    args = [
        "-i", str(video_path),
        "-vf", (
            f"subtitles={srt_path}:"
            f"force_style='FontName={font_name},"
            f"FontSize=28,PrimaryColour=&HFFFFFF,OutlineColour=&H000000,"
            f"Outline=2,Bold=1,Alignment=2,MarginV=60'"
        ),
        "-c:a", "copy",
        str(output_path),
    ]
    return _run_ffmpeg(args, "字幕焼き込み")


def generate_shorts_version(horizontal_video: Path, output_path: Path) -> bool:
    """
    横型動画（1920x1080）から縦型Shorts版（1080x1920）を生成
    中央部分をクロップしてリサイズ
    """
    args = [
        "-i", str(horizontal_video),
        "-vf",
        (
            f"crop=ih*9/16:ih,"           # アスペクト比 9:16 に切り抜き
            f"scale=1080:1920,"           # Shorts解像度にスケール
            f"setsar=1"
        ),
        "-c:a", "copy",
        "-c:v", "libx264", "-preset", "fast",
        "-crf", "23",
        str(output_path),
    ]
    return _run_ffmpeg(args, "Shorts版生成")


def compose_full_video(
    title_image:  Path,
    region_images: list[tuple[Path, Path | None]],  # (image, audio)
    outro_image:  Path,
    audio_main:   Path | None,
    bgm_path:     Path | None,
    srt_path:     Path | None,
    output_dir:   Path,
    date_str:     str,
) -> dict[str, Path]:
    """
    フルパイプラインで動画を合成する

    Args:
        title_image:    タイトルカード画像
        region_images:  [(地域画像, 音声ファイル), ...] のリスト
        outro_image:    エンディングカード画像
        audio_main:     全体ナレーション音声（地域別音声がない場合に使用）
        bgm_path:       BGM音声ファイル
        srt_path:       字幕SRTファイル
        output_dir:     出力ディレクトリ
        date_str:       日付文字列（ファイル名用）

    Returns:
        {"横型": Path, "縦型": Path}
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    clips_dir = output_dir / "clips"
    clips_dir.mkdir(exist_ok=True)

    clip_paths = []

    # 1. タイトルカード（音声なし・4秒）
    title_clip = clips_dir / "00_title.mp4"
    if image_to_video_clip(title_image, VIDEO_CONFIG["title_duration_sec"],
                             None, title_clip):
        clip_paths.append(title_clip)

    # 2. 地域別カード
    for i, (img, audio) in enumerate(region_images):
        region_clip = clips_dir / f"{i+1:02d}_region.mp4"
        dur = VIDEO_CONFIG["region_duration_sec"]
        if audio is None and audio_main:
            audio = audio_main  # フォールバック
        if image_to_video_clip(img, dur, audio, region_clip):
            clip_paths.append(region_clip)

    # 3. エンディングカード
    outro_clip = clips_dir / "99_outro.mp4"
    if image_to_video_clip(outro_image, VIDEO_CONFIG["outro_duration_sec"],
                             None, outro_clip):
        clip_paths.append(outro_clip)

    if not clip_paths:
        logger.error("有効なクリップが生成できませんでした")
        return {}

    # 4. クリップ連結
    concat_path = output_dir / f"weather_{date_str}_concat.mp4"
    if not concatenate_clips(clip_paths, concat_path):
        return {}

    # 5. BGM合成
    bgm_path_final = output_dir / f"weather_{date_str}_bgm.mp4"
    if bgm_path and bgm_path.exists():
        if not add_bgm(concat_path, bgm_path, bgm_path_final):
            bgm_path_final = concat_path
    else:
        bgm_path_final = concat_path

    # 6. 字幕焼き込み
    final_path = output_dir / f"weather_{date_str}.mp4"
    if srt_path and srt_path.exists():
        burn_subtitles(bgm_path_final, srt_path, final_path)
    else:
        import shutil
        shutil.copy(bgm_path_final, final_path)

    # 7. Shorts版
    shorts_path = output_dir / f"weather_{date_str}_shorts.mp4"
    generate_shorts_version(final_path, shorts_path)

    logger.info(f"動画合成完了: {final_path}")
    return {
        "horizontal": final_path,
        "shorts":     shorts_path if shorts_path.exists() else None,
    }


def generate_srt(script: str, regions: list[dict], audio_path: Path | None) -> str:
    """
    シンプルなSRT字幕を生成
    全体スクリプトを文単位で分割し、均等割り付け
    """
    sentences = [s.strip() + "。" for s in script.split("。") if s.strip()]
    if not sentences:
        return ""

    # 音声時間の推定（文字数 × 0.1秒 + 余白）
    total_duration = sum(len(s) * 0.1 + 0.5 for s in sentences)

    srt_lines = []
    current_time = 2.0  # タイトルカード分のオフセット

    for i, sentence in enumerate(sentences, 1):
        duration = len(sentence) * 0.1 + 0.5
        start = current_time
        end = current_time + duration

        def _fmt_time(t: float) -> str:
            h = int(t // 3600)
            m = int((t % 3600) // 60)
            s = int(t % 60)
            ms = int((t % 1) * 1000)
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

        srt_lines.append(str(i))
        srt_lines.append(f"{_fmt_time(start)} --> {_fmt_time(end)}")
        srt_lines.append(sentence)
        srt_lines.append("")

        current_time = end

    return "\n".join(srt_lines)
