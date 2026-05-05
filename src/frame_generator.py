# -*- coding: utf-8 -*-
"""
④ フレーム生成モジュール（Pillow）- プレゼンターキャラクター版
- 左側: キャラクター画像
- 右側: グラスモーフィズム風天気情報カード
"""

import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from config import COLORS, VIDEO_CONFIG, WEEKDAY_JA

logger = logging.getLogger(__name__)
JST = timezone(timedelta(hours=9))

PRESENTER_PATH = Path(__file__).parent.parent / "assets" / "presenter.png"


# ============================================================
# フォント
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
# 背景グラデーション
# ============================================================
def _make_gradient_bg(W: int, H: int) -> Image.Image:
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


# ============================================================
# キャラクター画像を左側に配置
# ============================================================
def _paste_presenter(img: Image.Image, W: int, H: int, presenter_w: int) -> Image.Image:
    if not PRESENTER_PATH.exists():
        return img
    try:
        char = Image.open(PRESENTER_PATH).convert("RGBA")
        # アスペクト比を保ちながらリサイズ（高さ=H基準）
        ratio = H / char.height
        new_w = int(char.width * ratio)
        char = char.resize((new_w, H), Image.LANCZOS)

        # 中央部分を presenter_w にクロップ
        if new_w > presenter_w:
            left = (new_w - presenter_w) // 2
            char = char.crop((left, 0, left + presenter_w, H))
        
        # 右端にグラデーションフェード（境界を自然に）
        fade = Image.new("L", char.size, 255)
        fade_draw = ImageDraw.Draw(fade)
        fade_w = 120
        for x in range(fade_w):
            alpha = int(255 * x / fade_w)
            fade_draw.line([(char.width - fade_w + x, 0),
                            (char.width - fade_w + x, H)], fill=alpha)
        char.putalpha(fade)

        img_rgba = img.convert("RGBA")
        img_rgba.paste(char, (0, 0), char)
        return img_rgba.convert("RGB")
    except Exception as e:
        logger.warning(f"キャラクター画像読み込み失敗: {e}")
        return img


# ============================================================
# ガラスカード
# ============================================================
def _draw_glass_card(img: Image.Image, xy: tuple, radius: int = 24,
                     alpha: int = 220, border_color: str = None) -> Image.Image:
    x0, y0, x1, y1 = xy
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    sdraw.rounded_rectangle([x0+4, y0+4, x1+4, y1+4], radius=radius,
                             fill=_hex_to_rgba(COLORS["shadow"], 70))
    base = img.convert("RGBA")
    base = Image.alpha_composite(base, shadow)

    card = Image.new("RGBA", img.size, (0, 0, 0, 0))
    cdraw = ImageDraw.Draw(card)
    cdraw.rounded_rectangle([x0, y0, x1, y1], radius=radius,
                             fill=(255, 255, 255, alpha))
    if border_color:
        cdraw.rounded_rectangle([x0, y0, x1, y1], radius=radius,
                                 outline=_hex_to_rgba(border_color, 160), width=2)
    base = Image.alpha_composite(base, card)
    return base.convert("RGB")


def _draw_gradient_banner(img: Image.Image, xy: tuple, radius: int = 16) -> Image.Image:
    x0, y0, x1, y1 = xy
    banner = Image.new("RGBA", img.size, (0, 0, 0, 0))
    c1 = _hex_to_rgb(COLORS["accent_gradient1"])
    c2 = _hex_to_rgb(COLORS["accent_gradient2"])
    bw = x1 - x0
    bdraw = ImageDraw.Draw(banner)
    for x in range(bw):
        r = int(c1[0] + (c2[0]-c1[0]) * x / bw)
        g = int(c1[1] + (c2[1]-c1[1]) * x / bw)
        b = int(c1[2] + (c2[2]-c1[2]) * x / bw)
        bdraw.line([(x0+x, y0), (x0+x, y1)], fill=(r, g, b, 230))
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=230)
    banner.putalpha(mask)
    result = img.convert("RGBA")
    result = Image.alpha_composite(result, banner)
    return result.convert("RGB")


def _draw_text_centered(draw, y: int, text: str, font, color: str, x0: int, x1: int):
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    x = x0 + (x1 - x0 - tw) // 2
    draw.text((x, y), text, font=font, fill=_hex_to_rgb(color))


# ============================================================
# タイトルカード
# ============================================================
def generate_title_frame(dt: datetime, output_path: Path) -> Path:
    W, H = VIDEO_CONFIG["width"], VIDEO_CONFIG["height"]
    img = _make_gradient_bg(W, H)

    # キャラクター（左40%）
    CHAR_W = int(W * 0.42)
    img = _paste_presenter(img, W, H, CHAR_W)

    # 右側コンテンツエリア
    RX = CHAR_W + 20
    img = _draw_glass_card(img, (RX, 80, W - 50, H - 80),
                           radius=32, alpha=230, border_color=COLORS["border"])
    draw = ImageDraw.Draw(img)

    font_title = _find_font(68, bold=True)
    font_date  = _find_font(42)
    font_sub   = _find_font(28)
    font_wm    = _find_font(20)

    weekday = WEEKDAY_JA[dt.weekday()]
    date_str = dt.strftime(f"%Y年%m月%d日（{weekday}）")

    MID_X = (RX + W - 50) // 2
    CX0, CX1 = RX, W - 50
    _draw_text_centered(draw, H//2 - 200, "☀  全国天気予報", font_title, COLORS["accent_blue"], CX0, CX1)
    draw.line([(RX+60, H//2-120), (W-110, H//2-120)],
              fill=_hex_to_rgb(COLORS["border"]), width=2)
    _draw_text_centered(draw, H//2 - 90, date_str, font_date, COLORS["text_primary"], CX0, CX1)
    _draw_text_centered(draw, H//2 + 10, "気象庁データをもとに毎朝7時更新", font_sub, COLORS["text_secondary"], CX0, CX1)
    _draw_text_centered(draw, H//2 + 70, "Japan Weather Forecast", font_sub, COLORS["text_secondary"], CX0, CX1)

    draw.text((RX + 30, H - 110), "データ出典：気象庁", font=font_wm,
              fill=_hex_to_rgb(COLORS["text_secondary"]))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "PNG")
    return output_path


# ============================================================
# 地域カード
# ============================================================
def generate_region_frame(region: dict, dt: datetime, output_path: Path) -> Path:
    W, H = VIDEO_CONFIG["width"], VIDEO_CONFIG["height"]
    img = _make_gradient_bg(W, H)

    CHAR_W = int(W * 0.38)
    img = _paste_presenter(img, W, H, CHAR_W)

    today    = region.get("today", {})
    tomorrow = region.get("tomorrow", {})
    warnings = region.get("warnings", [])
    weekly   = region.get("weekly", [])

    RX = CHAR_W + 15
    font_region = _find_font(48, bold=True)
    font_label  = _find_font(24)
    font_body   = _find_font(36, bold=True)
    font_small  = _find_font(26)
    font_tiny   = _find_font(20)
    font_emoji  = _find_font(64)

    # ヘッダーバナー
    img = _draw_gradient_banner(img, (RX, 20, W-40, 100), radius=18)
    draw = ImageDraw.Draw(img)
    _draw_text_centered(draw, 32, f"📍  {region['name']}の天気",
                        font_region, COLORS["text_white"], RX, W-40)

    # 今日カード
    img = _draw_glass_card(img, (RX, 112, RX + (W-RX-60)//2, 420),
                           radius=22, alpha=235, border_color=COLORS["border"])
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle([RX+20, 128, RX+100, 162], radius=10,
                            fill=_hex_to_rgb(COLORS["accent_blue"]))
    draw.text((RX+30, 131), "今日", font=font_label, fill=(255,255,255))

    draw.text((RX+20, 170), today.get("emoji","🌡"), font=font_emoji,
              fill=_hex_to_rgb(COLORS["text_primary"]))
    draw.text((RX+110, 192), today.get("weather","不明"), font=font_body,
              fill=_hex_to_rgb(COLORS["text_primary"]))
    draw.text((RX+20, 270), f"↑ {today.get('temp_max','--')}℃", font=font_body,
              fill=_hex_to_rgb(COLORS["temp_hot"]))
    draw.text((RX+20, 315), f"↓ {today.get('temp_min','--')}℃", font=font_body,
              fill=_hex_to_rgb(COLORS["temp_cold"]))
    draw.rounded_rectangle([RX+20, 362, RX+310, 402], radius=8,
                            fill=_hex_to_rgb(COLORS["bg_top"]))
    draw.text((RX+32, 368), f"☂ {today.get('pop','--')}%", font=font_small,
              fill=_hex_to_rgb(COLORS["text_secondary"]))

    # 明日カード
    TRX = RX + (W-RX-60)//2 + 20
    img = _draw_glass_card(img, (TRX, 112, W-40, 420),
                           radius=22, alpha=235, border_color=COLORS["border"])
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle([TRX+20, 128, TRX+100, 162], radius=10,
                            fill=_hex_to_rgb(COLORS["accent_gradient2"]))
    draw.text((TRX+30, 131), "明日", font=font_label, fill=(255,255,255))

    draw.text((TRX+20, 170), tomorrow.get("emoji","🌡"), font=font_emoji,
              fill=_hex_to_rgb(COLORS["text_primary"]))
    draw.text((TRX+110, 192), tomorrow.get("weather","不明"), font=font_body,
              fill=_hex_to_rgb(COLORS["text_primary"]))
    draw.text((TRX+20, 270), f"↑ {tomorrow.get('temp_max','--')}℃", font=font_body,
              fill=_hex_to_rgb(COLORS["temp_hot"]))
    draw.text((TRX+20, 315), f"↓ {tomorrow.get('temp_min','--')}℃", font=font_body,
              fill=_hex_to_rgb(COLORS["temp_cold"]))
    draw.rounded_rectangle([TRX+20, 362, TRX+310, 402], radius=8,
                            fill=_hex_to_rgb(COLORS["bg_top"]))
    draw.text((TRX+32, 368), f"☂ {tomorrow.get('pop','--')}%", font=font_small,
              fill=_hex_to_rgb(COLORS["text_secondary"]))

    # 週間予報
    if weekly:
        img = _draw_glass_card(img, (RX, 432, W-40, 620),
                               radius=18, alpha=215, border_color=COLORS["border"])
        draw = ImageDraw.Draw(img)
        draw.text((RX+20, 442), "7日間予報", font=font_label,
                  fill=_hex_to_rgb(COLORS["text_secondary"]))
        wc = min(len(weekly), 7)
        cw = (W - RX - 60) // max(wc, 1)
        for i, day in enumerate(weekly[:wc]):
            cx = RX + i * cw + cw // 2
            lbl = f"{day['date']}({day['weekday']})"
            bb = draw.textbbox((0,0), lbl, font=font_tiny)
            draw.text((cx-(bb[2]-bb[0])//2, 464), lbl, font=font_tiny,
                      fill=_hex_to_rgb(COLORS["text_secondary"]))
            draw.text((cx-16, 492), day.get("emoji",""), font=_find_font(30),
                      fill=_hex_to_rgb(COLORS["text_primary"]))
            ts = f"{day.get('temp_max','--')}/{day.get('temp_min','--')}℃"
            bb2 = draw.textbbox((0,0), ts, font=font_tiny)
            draw.text((cx-(bb2[2]-bb2[0])//2, 540), ts, font=font_tiny,
                      fill=_hex_to_rgb(COLORS["text_primary"]))

    # 警報
    if warnings:
        wy = 632
        img = _draw_glass_card(img, (RX, wy, W-40, wy+42*len(warnings[:3])+24),
                               radius=14, alpha=240, border_color=COLORS["warning_red"])
        draw = ImageDraw.Draw(img)
        for j, w in enumerate(warnings[:3]):
            draw.text((RX+20, wy+8+j*42), f"⚠  {w['area']}：{w['type']}",
                      font=font_small, fill=_hex_to_rgb(COLORS["warning_red"]))

    weekday_s = WEEKDAY_JA[dt.weekday()]
    draw.text((RX+20, H-44), f"気象庁データ　{dt.strftime(f'%m月%d日（{weekday_s}）')}",
              font=font_tiny, fill=_hex_to_rgb(COLORS["text_secondary"]))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "PNG")
    return output_path


# ============================================================
# エンディングカード
# ============================================================
def generate_outro_frame(dt: datetime, warnings_summary: list, output_path: Path) -> Path:
    W, H = VIDEO_CONFIG["width"], VIDEO_CONFIG["height"]
    img = _make_gradient_bg(W, H)

    CHAR_W = int(W * 0.42)
    img = _paste_presenter(img, W, H, CHAR_W)

    RX = CHAR_W + 20
    img = _draw_glass_card(img, (RX, 100, W-50, H-100),
                           radius=32, alpha=230, border_color=COLORS["border"])
    draw = ImageDraw.Draw(img)

    font_title = _find_font(46, bold=True)
    font_body  = _find_font(32)
    font_small = _find_font(24)
    CX0, CX1 = RX, W-50

    _draw_text_centered(draw, H//2 - 180, "本日もお気をつけて ☀",
                        font_title, COLORS["accent_blue"], CX0, CX1)
    draw.line([(RX+60, H//2-110), (W-110, H//2-110)],
              fill=_hex_to_rgb(COLORS["border"]), width=2)

    if warnings_summary:
        _draw_text_centered(draw, H//2-80, "【警報・注意報 発令中】",
                            font_body, COLORS["warning_red"], CX0, CX1)
        for i, msg in enumerate(warnings_summary[:4]):
            _draw_text_centered(draw, H//2-20+i*46, msg, font_small,
                                COLORS["text_primary"], CX0, CX1)
    else:
        _draw_text_centered(draw, H//2-40, "現在、警報・注意報は発令されていません",
                            font_body, COLORS["text_secondary"], CX0, CX1)
        _draw_text_centered(draw, H//2+30, "安全で穏やかな一日をお過ごしください",
                            font_small, COLORS["text_secondary"], CX0, CX1)

    draw.line([(RX+60, H//2+110), (W-110, H//2+110)],
              fill=_hex_to_rgb(COLORS["border"]), width=2)
    _draw_text_centered(draw, H//2+130, "データ出典：気象庁　毎朝7時更新",
                        font_small, COLORS["text_secondary"], CX0, CX1)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "PNG")
    return output_path
