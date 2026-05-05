# -*- coding: utf-8 -*-
"""
④ フレーム生成モジュール（Pillow）
- グラスモーフィズム風ライトデザイン
- タイトルカード・地域カード・エンディングカードを生成
"""

import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter

from config import COLORS, VIDEO_CONFIG, WEEKDAY_JA

logger = logging.getLogger(__name__)
JST = timezone(timedelta(hours=9))


# ============================================================
# フォント設定
# ============================================================

def _find_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
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
    return ImageFont.load_default()


def _hex_to_rgb(hex_color: str) -> tuple:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _hex_to_rgba(hex_color: str, alpha: int = 255) -> tuple:
    r, g, b = _hex_to_rgb(hex_color)
    return (r, g, b, alpha)


# ============================================================
# グラデーション背景
# ============================================================

def _make_gradient_bg(W: int, H: int) -> Image.Image:
    """空色→白のグラデーション背景"""
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)

    top = _hex_to_rgb(COLORS["bg_top"])
    bot = _hex_to_rgb(COLORS["bg_bottom"])

    for y in range(H):
        r = int(top[0] + (bot[0] - top[0]) * y / H)
        g = int(top[1] + (bot[1] - top[1]) * y / H)
        b = int(top[2] + (bot[2] - top[2]) * y / H)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    return img


def _make_base_frame(W: int, H: int) -> tuple:
    img = _make_gradient_bg(W, H)
    draw = ImageDraw.Draw(img)
    return img, draw


# ============================================================
# ガラスカード描画（シャドウ付き角丸）
# ============================================================

def _draw_glass_card(img: Image.Image, xy: tuple, radius: int = 24,
                     alpha: int = 220, border_color: str = None):
    """半透明白カードをガラス風に描画"""
    x0, y0, x1, y1 = xy

    # シャドウ（薄いブルー、オフセット）
    shadow_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow_layer)
    sdraw.rounded_rectangle(
        [x0 + 4, y0 + 4, x1 + 4, y1 + 4],
        radius=radius,
        fill=_hex_to_rgba(COLORS["shadow"], 80)
    )
    img_rgba = img.convert("RGBA")
    img_rgba = Image.alpha_composite(img_rgba, shadow_layer)

    # カード本体（半透明白）
    card_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    cdraw = ImageDraw.Draw(card_layer)
    cdraw.rounded_rectangle(
        [x0, y0, x1, y1],
        radius=radius,
        fill=(255, 255, 255, alpha)
    )
    if border_color:
        cdraw.rounded_rectangle(
            [x0, y0, x1, y1],
            radius=radius,
            outline=_hex_to_rgba(border_color, 180),
            width=2
        )
    img_rgba = Image.alpha_composite(img_rgba, card_layer)
    return img_rgba.convert("RGB")


def _draw_gradient_banner(img: Image.Image, xy: tuple, radius: int = 16) -> Image.Image:
    """グラデーションバナーを描画"""
    x0, y0, x1, y1 = xy
    banner = Image.new("RGBA", img.size, (0, 0, 0, 0))
    bdraw = ImageDraw.Draw(banner)

    c1 = _hex_to_rgb(COLORS["accent_gradient1"])
    c2 = _hex_to_rgb(COLORS["accent_gradient2"])
    W_banner = x1 - x0

    for x in range(W_banner):
        r = int(c1[0] + (c2[0] - c1[0]) * x / W_banner)
        g = int(c1[1] + (c2[1] - c1[1]) * x / W_banner)
        b = int(c1[2] + (c2[2] - c1[2]) * x / W_banner)
        bdraw.line([(x0 + x, y0), (x0 + x, y1)], fill=(r, g, b, 240))

    # 角丸マスク
    mask = Image.new("L", img.size, 0)
    mdraw = ImageDraw.Draw(mask)
    mdraw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=240)
    banner.putalpha(mask)

    result = img.convert("RGBA")
    result = Image.alpha_composite(result, banner)
    return result.convert("RGB")


def _draw_text_centered(draw, y: int, text: str, font, color: str, W: int):
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    x = (W - tw) // 2
    draw.text((x, y), text, font=font, fill=_hex_to_rgb(color))


def _draw_stat_item(draw, x: int, y: int, icon: str, label: str, value: str,
                    font_icon, font_label, font_val, color_label: str, color_val: str):
    """統計アイテム（アイコン＋ラベル＋値）"""
    draw.text((x, y), icon, font=font_icon, fill=_hex_to_rgb(COLORS["accent_blue"]))
    draw.text((x, y + 42), label, font=font_label, fill=_hex_to_rgb(color_label))
    draw.text((x, y + 68), value, font=font_val, fill=_hex_to_rgb(color_val))


# ============================================================
# タイトルカード
# ============================================================

def generate_title_frame(dt: datetime, output_path: Path) -> Path:
    W, H = VIDEO_CONFIG["width"], VIDEO_CONFIG["height"]
    img, draw = _make_base_frame(W, H)

    weekday = WEEKDAY_JA[dt.weekday()]
    date_str = dt.strftime(f"%Y年%m月%d日（{weekday}）")

    # メインカード
    img = _draw_glass_card(img, (W//2 - 560, H//2 - 200, W//2 + 560, H//2 + 220),
                           radius=32, alpha=230, border_color=COLORS["border"])
    draw = ImageDraw.Draw(img)

    font_title = _find_font(72, bold=True)
    font_date  = _find_font(46)
    font_sub   = _find_font(30)
    font_wm    = _find_font(22)

    # アクセントライン
    draw.rectangle([(W//2 - 560, H//2 - 200), (W//2 + 560, H//2 - 185)],
                   fill=_hex_to_rgb(COLORS["accent_blue"]))

    _draw_text_centered(draw, H//2 - 170, "☀ 全国天気予報", font_title, COLORS["accent_blue"], W)
    _draw_text_centered(draw, H//2 - 55,  date_str, font_date, COLORS["text_primary"], W)
    _draw_text_centered(draw, H//2 + 55,  "気象庁データをもとに毎朝7時更新", font_sub, COLORS["text_secondary"], W)

    # 下部区切り線
    draw.line([(W//2 - 400, H//2 + 110), (W//2 + 400, H//2 + 110)],
              fill=_hex_to_rgb(COLORS["border"]), width=2)
    _draw_text_centered(draw, H//2 + 130, "Japan Weather Forecast", font_sub, COLORS["text_secondary"], W)

    # ウォーターマーク
    draw.text((40, H - 50), "データ出典：気象庁", font=font_wm,
              fill=_hex_to_rgb(COLORS["text_secondary"]))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "PNG")
    return output_path


# ============================================================
# 地域カード
# ============================================================

def generate_region_frame(region: dict, dt: datetime, output_path: Path) -> Path:
    W, H = VIDEO_CONFIG["width"], VIDEO_CONFIG["height"]
    img, _ = _make_base_frame(W, H)

    today    = region.get("today", {})
    tomorrow = region.get("tomorrow", {})
    warnings = region.get("warnings", [])
    weekly   = region.get("weekly", [])

    # ---- ヘッダーバナー ----
    img = _draw_gradient_banner(img, (50, 24, W - 50, 108), radius=20)
    draw = ImageDraw.Draw(img)

    font_region = _find_font(54, bold=True)
    font_label  = _find_font(26)
    font_body   = _find_font(40, bold=True)
    font_small  = _find_font(28)
    font_tiny   = _find_font(22)
    font_emoji  = _find_font(72)
    font_icon   = _find_font(30)

    _draw_text_centered(draw, 36, f"📍 {region['name']}の天気", font_region,
                        COLORS["text_white"], W)

    # ---- 今日カード（左）----
    img = _draw_glass_card(img, (50, 125, W//2 - 20, 460),
                           radius=24, alpha=235, border_color=COLORS["border"])
    draw = ImageDraw.Draw(img)

    # 「今日」ラベル
    draw.rounded_rectangle([70, 140, 150, 175], radius=10,
                            fill=_hex_to_rgb(COLORS["accent_blue"]))
    draw.text((82, 143), "今日", font=font_label, fill=(255, 255, 255))

    # 天気絵文字＋天気名
    draw.text((70, 185), today.get("emoji", "🌡"), font=font_emoji,
              fill=_hex_to_rgb(COLORS["text_primary"]))
    draw.text((185, 215), today.get("weather", "不明"), font=font_body,
              fill=_hex_to_rgb(COLORS["text_primary"]))

    # 気温
    draw.text((70, 305), f"↑ {today.get('temp_max','--')}℃", font=font_body,
              fill=_hex_to_rgb(COLORS["temp_hot"]))
    draw.text((280, 305), f"↓ {today.get('temp_min','--')}℃", font=font_body,
              fill=_hex_to_rgb(COLORS["temp_cold"]))

    # 降水確率
    draw.rounded_rectangle([70, 370, 70 + 340, 415], radius=10,
                            fill=_hex_to_rgb(COLORS["bg_top"]))
    draw.text((88, 376), f"☂  降水確率  {today.get('pop','--')}%", font=font_small,
              fill=_hex_to_rgb(COLORS["text_secondary"]))

    # ---- 明日カード（右）----
    img = _draw_glass_card(img, (W//2 + 20, 125, W - 50, 460),
                           radius=24, alpha=235, border_color=COLORS["border"])
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle([W//2 + 40, 140, W//2 + 128, 175], radius=10,
                            fill=_hex_to_rgb(COLORS["accent_gradient2"]))
    draw.text((W//2 + 52, 143), "明日", font=font_label, fill=(255, 255, 255))

    draw.text((W//2 + 40, 185), tomorrow.get("emoji", "🌡"), font=font_emoji,
              fill=_hex_to_rgb(COLORS["text_primary"]))
    draw.text((W//2 + 155, 215), tomorrow.get("weather", "不明"), font=font_body,
              fill=_hex_to_rgb(COLORS["text_primary"]))

    draw.text((W//2 + 40, 305), f"↑ {tomorrow.get('temp_max','--')}℃", font=font_body,
              fill=_hex_to_rgb(COLORS["temp_hot"]))
    draw.text((W//2 + 250, 305), f"↓ {tomorrow.get('temp_min','--')}℃", font=font_body,
              fill=_hex_to_rgb(COLORS["temp_cold"]))

    draw.rounded_rectangle([W//2 + 40, 370, W//2 + 380, 415], radius=10,
                            fill=_hex_to_rgb(COLORS["bg_top"]))
    draw.text((W//2 + 58, 376), f"☂  降水確率  {tomorrow.get('pop','--')}%", font=font_small,
              fill=_hex_to_rgb(COLORS["text_secondary"]))

    # ---- 週間予報 ----
    if weekly:
        img = _draw_glass_card(img, (50, 475, W - 50, 660),
                               radius=20, alpha=220, border_color=COLORS["border"])
        draw = ImageDraw.Draw(img)

        draw.text((75, 485), "7日間の予報", font=font_label,
                  fill=_hex_to_rgb(COLORS["text_secondary"]))

        week_count = min(len(weekly), 7)
        col_w = (W - 100) // max(week_count, 1)
        for i, day in enumerate(weekly[:week_count]):
            cx = 50 + i * col_w + col_w // 2

            # 曜日ラベル
            day_label = f"{day['date']}({day['weekday']})"
            bb = draw.textbbox((0, 0), day_label, font=font_tiny)
            draw.text((cx - (bb[2]-bb[0])//2, 510), day_label,
                      font=font_tiny, fill=_hex_to_rgb(COLORS["text_secondary"]))

            # 絵文字
            draw.text((cx - 18, 537), day.get("emoji", ""), font=_find_font(34),
                      fill=_hex_to_rgb(COLORS["text_primary"]))

            # 気温
            temp_str = f"{day.get('temp_max','--')}/{day.get('temp_min','--')}℃"
            bb2 = draw.textbbox((0, 0), temp_str, font=font_tiny)
            draw.text((cx - (bb2[2]-bb2[0])//2, 587), temp_str,
                      font=font_tiny, fill=_hex_to_rgb(COLORS["text_primary"]))

    # ---- 警報・注意報 ----
    if warnings:
        warn_y = 670
        img = _draw_glass_card(img, (50, warn_y, W - 50, warn_y + 44 * len(warnings[:3]) + 30),
                               radius=16, alpha=240, border_color=COLORS["warning_red"])
        draw = ImageDraw.Draw(img)
        for j, w in enumerate(warnings[:3]):
            msg = f"⚠  {w['area']}：{w['type']}"
            draw.text((80, warn_y + 10 + j * 44), msg, font=font_small,
                      fill=_hex_to_rgb(COLORS["warning_red"]))

    # 出典
    weekday_str = WEEKDAY_JA[dt.weekday()]
    date_str = dt.strftime(f"%m月%d日（{weekday_str}）")
    draw.text((40, H - 48), f"気象庁データ　{date_str}", font=font_tiny,
              fill=_hex_to_rgb(COLORS["text_secondary"]))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "PNG")
    return output_path


# ============================================================
# エンディングカード
# ============================================================

def generate_outro_frame(dt: datetime, warnings_summary: list, output_path: Path) -> Path:
    W, H = VIDEO_CONFIG["width"], VIDEO_CONFIG["height"]
    img, draw = _make_base_frame(W, H)

    img = _draw_glass_card(img, (W//2 - 580, H//2 - 230, W//2 + 580, H//2 + 230),
                           radius=32, alpha=235, border_color=COLORS["border"])
    draw = ImageDraw.Draw(img)

    font_title = _find_font(52, bold=True)
    font_body  = _find_font(34)
    font_small = _find_font(26)

    draw.rectangle([(W//2 - 580, H//2 - 230), (W//2 + 580, H//2 - 215)],
                   fill=_hex_to_rgb(COLORS["accent_blue"]))

    _draw_text_centered(draw, H//2 - 195, "本日もお気をつけてお過ごしください ☀",
                        font_title, COLORS["accent_blue"], W)

    draw.line([(W//2 - 420, H//2 - 130), (W//2 + 420, H//2 - 130)],
              fill=_hex_to_rgb(COLORS["border"]), width=2)

    if warnings_summary:
        _draw_text_centered(draw, H//2 - 110, "【警報・注意報 発令中エリア】",
                            font_body, COLORS["warning_red"], W)
        for i, msg in enumerate(warnings_summary[:4]):
            _draw_text_centered(draw, H//2 - 50 + i * 48, msg,
                                font_small, COLORS["text_primary"], W)
    else:
        _draw_text_centered(draw, H//2 - 60, "現在、警報・注意報は発令されていません",
                            font_body, COLORS["text_secondary"], W)
        _draw_text_centered(draw, H//2 + 20, "安全で穏やかな一日をお過ごしください",
                            font_small, COLORS["text_secondary"], W)

    draw.line([(W//2 - 420, H//2 + 120), (W//2 + 420, H//2 + 120)],
              fill=_hex_to_rgb(COLORS["border"]), width=2)

    _draw_text_centered(draw, H//2 + 140, "データ出典：気象庁　毎朝7時更新",
                        font_small, COLORS["text_secondary"], W)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "PNG")
    return output_path
