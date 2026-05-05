"""
④ フレーム生成モジュール（Pillow）
- NHKスタイルの天気予報フレームを画像として生成
- タイトルカード・地域カード・エンディングカードを生成
- 外部ライブラリ：Pillow / noto-sans-cjk フォント
"""

import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from config import COLORS, VIDEO_CONFIG, WEEKDAY_JA

logger = logging.getLogger(__name__)
JST = timezone(timedelta(hours=9))

# ============================================================
# フォント設定
# ============================================================

def _find_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """
    Noto Sans CJK JP フォントを検索して返す（なければデフォルト）
    GitHub Actions (Ubuntu) では apt install fonts-noto-cjk で導入済み
    """
    candidates = [
        # Ubuntu / GitHub Actions
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        # macOS
        "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
        "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
        "/Library/Fonts/NotoSansCJKjp-Bold.otf",
        "/Library/Fonts/NotoSansCJKjp-Regular.otf",
    ]

    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue

    logger.warning("CJKフォントが見つかりません。デフォルトフォントを使用します。")
    return ImageFont.load_default()


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


# ============================================================
# ベースフレーム描画
# ============================================================

def _make_base_frame(W: int, H: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    """背景グラデーション付きのベースフレームを生成"""
    img = Image.new("RGB", (W, H), _hex_to_rgb(COLORS["bg_primary"]))
    draw = ImageDraw.Draw(img)

    # 上部グラデーション風（水平ライン）
    for y in range(H // 3):
        ratio = y / (H // 3)
        r = int(13 + (26 - 13) * ratio)
        g = int(27 + (47 - 27) * ratio)
        b = int(42 + (69 - 42) * ratio)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # 上部アクセントライン
    draw.rectangle([(0, 0), (W, 8)], fill=_hex_to_rgb(COLORS["accent_blue"]))
    draw.rectangle([(0, 8), (W, 12)], fill=_hex_to_rgb(COLORS["accent_yellow"]))

    return img, draw


def _draw_text_centered(draw: ImageDraw.ImageDraw, y: int, text: str,
                         font: ImageFont.FreeTypeFont, color: str, W: int,
                         shadow: bool = True):
    """センタリングしてテキストを描画（シャドウ付き）"""
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    x = (W - tw) // 2
    if shadow:
        draw.text((x + 2, y + 2), text, font=font, fill=(0, 0, 0, 128))
    draw.text((x, y), text, font=font, fill=_hex_to_rgb(color))


def _draw_rounded_rect(draw: ImageDraw.ImageDraw, xy: tuple, fill: str,
                        radius: int = 16, outline: str | None = None):
    """角丸矩形を描画"""
    x0, y0, x1, y1 = xy
    fill_rgb = _hex_to_rgb(fill)
    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius,
                            fill=fill_rgb,
                            outline=_hex_to_rgb(outline) if outline else None,
                            width=2 if outline else 0)


# ============================================================
# タイトルカード
# ============================================================

def generate_title_frame(dt: datetime, output_path: Path) -> Path:
    """
    オープニングタイトルカードを生成
    「全国天気予報 / ○年○月○日（曜）/ 朝7時更新」
    """
    W, H = VIDEO_CONFIG["width"], VIDEO_CONFIG["height"]
    img, draw = _make_base_frame(W, H)

    weekday = WEEKDAY_JA[dt.weekday()]
    date_str = dt.strftime(f"%Y年%m月%d日（{weekday}）")

    # メインロゴエリア
    _draw_rounded_rect(draw, (W//2 - 500, H//2 - 160, W//2 + 500, H//2 + 160),
                        fill=COLORS["bg_card"], outline=COLORS["accent_blue"], radius=24)

    font_title = _find_font(64, bold=True)
    font_date  = _find_font(44)
    font_sub   = _find_font(30)

    _draw_text_centered(draw, H//2 - 130, "🌤 全国天気予報", font_title, COLORS["accent_yellow"], W)
    _draw_text_centered(draw, H//2 - 30,  date_str, font_date, COLORS["text_primary"], W)
    _draw_text_centered(draw, H//2 + 60,  "気象庁データをもとに毎朝7時更新", font_sub, COLORS["text_secondary"], W)

    # 下部ウォーターマーク
    font_wm = _find_font(22)
    draw.text((40, H - 50), "データ出典：気象庁", font=font_wm,
               fill=_hex_to_rgb(COLORS["text_secondary"]))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "PNG")
    logger.debug(f"タイトルカード生成: {output_path}")
    return output_path


# ============================================================
# 地域カード（メインコンテンツ）
# ============================================================

def generate_region_frame(region: dict, dt: datetime, output_path: Path) -> Path:
    """
    地域別天気カードを生成
    """
    W, H = VIDEO_CONFIG["width"], VIDEO_CONFIG["height"]
    img, draw = _make_base_frame(W, H)

    today = region.get("today", {})
    tomorrow = region.get("tomorrow", {})
    warnings = region.get("warnings", [])
    weekly = region.get("weekly", [])

    # ---- ヘッダー ----
    font_region = _find_font(56, bold=True)
    font_label  = _find_font(28)
    font_body   = _find_font(38, bold=True)
    font_small  = _find_font(26)
    font_tiny   = _find_font(22)

    # 地域名バナー
    _draw_rounded_rect(draw, (60, 30, W - 60, 110),
                        fill=COLORS["accent_blue"], radius=16)
    _draw_text_centered(draw, 44, f"📍 {region['name']}の天気", font_region, COLORS["text_primary"], W)

    # ---- 今日の天気カード（左）----
    card_l = (60, 130, W//2 - 30, 440)
    _draw_rounded_rect(draw, card_l, fill=COLORS["bg_card"], outline=COLORS["border"], radius=20)

    draw.text((90, 150), "今日", font=font_label, fill=_hex_to_rgb(COLORS["text_secondary"]))
    emoji_today = today.get("emoji", "🌡️")
    draw.text((90, 185), emoji_today, font=_find_font(80), fill=_hex_to_rgb(COLORS["text_primary"]))
    draw.text((195, 205), today.get("weather", "不明"), font=font_body,
               fill=_hex_to_rgb(COLORS["text_primary"]))

    # 気温
    t_max = today.get("temp_max", "--")
    t_min = today.get("temp_min", "--")
    draw.text((90, 295), f"最高 {t_max}℃", font=font_body,
               fill=_hex_to_rgb(COLORS["temp_hot"]))
    draw.text((90, 345), f"最低 {t_min}℃", font=font_body,
               fill=_hex_to_rgb(COLORS["temp_cold"]))

    # 降水確率
    pop = today.get("pop", "--")
    draw.text((90, 405), f"☂ 降水確率 {pop}%", font=font_small,
               fill=_hex_to_rgb(COLORS["text_secondary"]))

    # ---- 明日の天気カード（右）----
    card_r = (W//2 + 30, 130, W - 60, 440)
    _draw_rounded_rect(draw, card_r, fill=COLORS["bg_card"], outline=COLORS["border"], radius=20)

    draw.text((W//2 + 60, 150), "明日", font=font_label, fill=_hex_to_rgb(COLORS["text_secondary"]))
    emoji_tom = tomorrow.get("emoji", "🌡️")
    draw.text((W//2 + 60, 185), emoji_tom, font=_find_font(80), fill=_hex_to_rgb(COLORS["text_primary"]))
    draw.text((W//2 + 165, 205), tomorrow.get("weather", "不明"), font=font_body,
               fill=_hex_to_rgb(COLORS["text_primary"]))

    t_max_tom = tomorrow.get("temp_max", "--")
    t_min_tom = tomorrow.get("temp_min", "--")
    draw.text((W//2 + 60, 295), f"最高 {t_max_tom}℃", font=font_body,
               fill=_hex_to_rgb(COLORS["temp_hot"]))
    draw.text((W//2 + 60, 345), f"最低 {t_min_tom}℃", font=font_body,
               fill=_hex_to_rgb(COLORS["temp_cold"]))
    pop_tom = tomorrow.get("pop", "--")
    draw.text((W//2 + 60, 405), f"☂ 降水確率 {pop_tom}%", font=font_small,
               fill=_hex_to_rgb(COLORS["text_secondary"]))

    # ---- 週間予報（下段）----
    if weekly:
        _draw_rounded_rect(draw, (60, 460, W - 60, 630),
                            fill=COLORS["bg_card"], outline=COLORS["border"], radius=16)
        draw.text((90, 470), "週間予報", font=font_label,
                   fill=_hex_to_rgb(COLORS["text_secondary"]))

        week_count = min(len(weekly), 7)
        col_w = (W - 120) // max(week_count, 1)
        for i, day in enumerate(weekly[:week_count]):
            cx = 60 + i * col_w + col_w // 2

            # 曜日
            day_label = f"{day['date']}({day['weekday']})"
            bb = draw.textbbox((0, 0), day_label, font=font_tiny)
            draw.text((cx - (bb[2]-bb[0])//2, 498), day_label,
                       font=font_tiny, fill=_hex_to_rgb(COLORS["text_secondary"]))
            # 天気絵文字
            draw.text((cx - 18, 526), day.get("emoji", ""), font=_find_font(36),
                       fill=_hex_to_rgb(COLORS["text_primary"]))
            # 気温
            temp_str = f"{day.get('temp_max','--')}/{day.get('temp_min','--')}℃"
            bb2 = draw.textbbox((0, 0), temp_str, font=font_tiny)
            draw.text((cx - (bb2[2]-bb2[0])//2, 576), temp_str,
                       font=font_tiny, fill=_hex_to_rgb(COLORS["text_secondary"]))

    # ---- 警報・注意報（ある場合）----
    if warnings:
        warn_msgs = [f"⚠ {w['area']}：{w['type']}" for w in warnings[:3]]
        _draw_rounded_rect(draw, (60, 650, W - 60, 650 + 40 * len(warn_msgs) + 20),
                            fill="#4A0000", outline=COLORS["warning_red"], radius=12)
        for j, msg in enumerate(warn_msgs):
            draw.text((90, 660 + j * 40), msg, font=font_small,
                       fill=_hex_to_rgb(COLORS["warning_red"]))

    # 出典
    weekday = WEEKDAY_JA[dt.weekday()]
    date_str = dt.strftime(f"%m月%d日（{weekday}）")
    draw.text((40, H - 50), f"気象庁データ　{date_str}", font=font_tiny,
               fill=_hex_to_rgb(COLORS["text_secondary"]))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "PNG")
    logger.debug(f"地域カード生成: {output_path}")
    return output_path


# ============================================================
# エンディングカード
# ============================================================

def generate_outro_frame(dt: datetime, warnings_summary: list[str], output_path: Path) -> Path:
    """エンディングカードを生成"""
    W, H = VIDEO_CONFIG["width"], VIDEO_CONFIG["height"]
    img, draw = _make_base_frame(W, H)

    font_title = _find_font(52, bold=True)
    font_body  = _find_font(34)
    font_small = _find_font(26)

    _draw_rounded_rect(draw, (W//2 - 560, H//2 - 200, W//2 + 560, H//2 + 200),
                        fill=COLORS["bg_card"], outline=COLORS["accent_blue"], radius=24)

    _draw_text_centered(draw, H//2 - 170, "本日もお気をつけてお過ごしください", font_title,
                         COLORS["accent_yellow"], W)

    if warnings_summary:
        _draw_text_centered(draw, H//2 - 80, "【警報・注意報発令中エリア】", font_body,
                             COLORS["warning_red"], W)
        for i, msg in enumerate(warnings_summary[:4]):
            _draw_text_centered(draw, H//2 - 20 + i * 48, msg, font_small,
                                 COLORS["text_primary"], W)
    else:
        _draw_text_centered(draw, H//2 - 20, "現在、警報・注意報は発令されていません", font_body,
                             COLORS["text_secondary"], W)

    _draw_text_centered(draw, H//2 + 130, "データ出典：気象庁　🌤 毎朝7時更新",
                         font_small, COLORS["text_secondary"], W)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "PNG")
    logger.debug(f"エンディングカード生成: {output_path}")
    return output_path
