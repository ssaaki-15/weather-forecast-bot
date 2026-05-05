"""
① 気象庁 API データ取得モジュール
- 気象庁の公開JSONエンドポイントを利用（APIキー不要・完全無料）
- 1日1回の更新に最適化
"""

import json
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Optional
import urllib.request
import urllib.error

from config import JMA_REGIONS, JMA_NATIONAL_OVERVIEW_CODE, WEATHER_CODE_MAP, WEEKDAY_JA

logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))

# 気象庁 API エンドポイント
JMA_BASE = "https://www.jma.go.jp/bosai"
JMA_FORECAST_URL   = f"{JMA_BASE}/forecast/data/forecast/{{code}}.json"
JMA_OVERVIEW_URL   = f"{JMA_BASE}/forecast/data/overview_forecast/{{code}}.json"
JMA_WARNING_URL    = f"{JMA_BASE}/warning/data/warning/{{code}}.json"

# アクセス間隔（サーバーへの配慮）
REQUEST_INTERVAL_SEC = 1.5


def _fetch_json(url: str) -> Optional[dict | list]:
    """HTTPリクエストでJSONを取得"""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "WeatherForecastBot/1.0 (educational use)"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            logger.debug(f"Fetched: {url}")
            return data
    except urllib.error.HTTPError as e:
        logger.error(f"HTTP {e.code}: {url}")
        return None
    except Exception as e:
        logger.error(f"Fetch error ({url}): {e}")
        return None


def _parse_weather_code(code: str) -> tuple[str, str]:
    """天気コードから（天気テキスト, 絵文字）を返す"""
    return WEATHER_CODE_MAP.get(code, ("不明", "🌡️"))


def _parse_forecast(data: list) -> dict:
    """
    気象庁 forecast JSON を解析して整形データを返す

    Returns:
        {
          "today": {"weather": str, "emoji": str, "pop": str, "temp_max": str, "temp_min": str},
          "tomorrow": {...},
          "weekly": [{"date": str, "weather": str, "emoji": str, "pop_max": str, "temp_max": str, "temp_min": str}, ...]
        }
    """
    result = {"today": {}, "tomorrow": {}, "weekly": []}
    if not data or not isinstance(data, list):
        return result

    try:
        # --- 今日・明日の天気（data[0] のtimeSeries[0]） ---
        ts0 = data[0]["timeSeries"]

        # 天気コード・天気テキスト（最初のareaを代表値として使用）
        weather_series = ts0[0]
        area0 = weather_series["areas"][0]
        codes = area0.get("weatherCodes", [])
        weathers = area0.get("weathers", [])

        # 降水確率（timeSeries[1]）
        pop_series = ts0[1] if len(ts0) > 1 else {}
        pop_areas = pop_series.get("areas", [{}])
        pops = pop_areas[0].get("pops", []) if pop_areas else []

        # 気温（timeSeries[2]）
        temp_series = ts0[2] if len(ts0) > 2 else {}
        temp_areas = temp_series.get("areas", [{}])
        temps = temp_areas[0].get("temps", []) if temp_areas else []

        def _safe(lst, idx, fallback="--"):
            return lst[idx] if lst and idx < len(lst) else fallback

        # 今日
        w_text, w_emoji = _parse_weather_code(_safe(codes, 0, ""))
        result["today"] = {
            "weather": w_text or _safe(weathers, 0, "不明"),
            "emoji":   w_emoji,
            "pop":     _safe(pops, 0),
            "temp_max": _safe(temps, 1),
            "temp_min": _safe(temps, 0),
        }

        # 明日
        w_text, w_emoji = _parse_weather_code(_safe(codes, 1, ""))
        result["tomorrow"] = {
            "weather": w_text or _safe(weathers, 1, "不明"),
            "emoji":   w_emoji,
            "pop":     _safe(pops, 2),
            "temp_max": _safe(temps, 3),
            "temp_min": _safe(temps, 2),
        }

        # --- 週間予報（data[1]）---
        if len(data) > 1:
            weekly_ts = data[1].get("timeSeries", [])
            if weekly_ts:
                wk_weather = weekly_ts[0]
                wk_area = wk_weather.get("areas", [{}])[0]
                wk_codes = wk_area.get("weatherCodes", [])
                wk_time_defines = wk_weather.get("timeDefines", [])

                wk_temps = []
                if len(weekly_ts) > 1:
                    wk_temp_area = weekly_ts[1].get("areas", [{}])[0]
                    wk_max = wk_temp_area.get("tempsMax", [])
                    wk_min = wk_temp_area.get("tempsMin", [])
                    wk_pop  = wk_temp_area.get("pops", [])
                else:
                    wk_max = wk_min = wk_pop = []

                for i, td in enumerate(wk_time_defines[:7]):
                    dt = datetime.fromisoformat(td).astimezone(JST)
                    wt, we = _parse_weather_code(_safe(wk_codes, i, ""))
                    result["weekly"].append({
                        "date":     dt.strftime("%m/%d"),
                        "weekday":  WEEKDAY_JA[dt.weekday()],
                        "weather":  wt,
                        "emoji":    we,
                        "temp_max": _safe(wk_max, i),
                        "temp_min": _safe(wk_min, i),
                        "pop":      _safe(wk_pop, i),
                    })

    except (KeyError, IndexError, TypeError) as e:
        logger.warning(f"Parse error in forecast data: {e}")

    return result


def _parse_warnings(data: dict) -> list[dict]:
    """
    警報・注意報データを解析

    Returns:
        [{"area": str, "type": str, "level": str}, ...]
    """
    warnings = []
    if not data:
        return warnings
    try:
        areas = data.get("areaTypes", [])
        for area_type in areas:
            for area in area_type.get("areas", []):
                area_name = area.get("name", "")
                for warn in area.get("warnings", []):
                    if warn.get("status") in ("発表", "継続"):
                        warnings.append({
                            "area":  area_name,
                            "type":  warn.get("type", ""),
                            "level": warn.get("level", ""),
                            "status": warn.get("status", ""),
                        })
    except Exception as e:
        logger.warning(f"Warning parse error: {e}")
    return warnings


def fetch_national_overview() -> str:
    """全国概況テキストを取得"""
    url = JMA_OVERVIEW_URL.format(code=JMA_NATIONAL_OVERVIEW_CODE)
    data = _fetch_json(url)
    time.sleep(REQUEST_INTERVAL_SEC)
    if not data:
        return "全国概況データを取得できませんでした。"
    return data.get("text", data.get("headlineText", ""))


def fetch_all_regions() -> list[dict]:
    """
    全地方の気象データを取得・整形して返す

    Returns:
        [
          {
            "key": "hokkaido",
            "name": "北海道",
            "today": {...},
            "tomorrow": {...},
            "weekly": [...],
            "warnings": [...],
          },
          ...
        ]
    """
    results = []
    total = len(JMA_REGIONS)

    for i, region in enumerate(JMA_REGIONS):
        logger.info(f"[{i+1}/{total}] {region['name']} を取得中...")

        # 予報データ取得
        forecast_url = JMA_FORECAST_URL.format(code=region["code"])
        forecast_raw = _fetch_json(forecast_url)
        time.sleep(REQUEST_INTERVAL_SEC)

        # 警報データ取得
        warning_url = JMA_WARNING_URL.format(code=region["code"])
        warning_raw = _fetch_json(warning_url)
        time.sleep(REQUEST_INTERVAL_SEC)

        # パース
        forecast = _parse_forecast(forecast_raw or [])
        warnings = _parse_warnings(warning_raw or {})

        results.append({
            **region,
            "today":    forecast["today"],
            "tomorrow": forecast["tomorrow"],
            "weekly":   forecast["weekly"],
            "warnings": warnings,
        })

    return results


def format_region_data_for_prompt(regions: list[dict]) -> str:
    """LLMプロンプト用の地域データ文字列を生成"""
    lines = []
    for r in regions:
        td = r.get("today", {})
        lines.append(
            f"【{r['name']}】"
            f"天気: {td.get('weather','不明')} "
            f"/ 最高{td.get('temp_max','--')}℃ "
            f"/ 最低{td.get('temp_min','--')}℃ "
            f"/ 降水確率{td.get('pop','--')}%"
        )
    return "\n".join(lines)


def format_warnings_for_prompt(regions: list[dict]) -> str:
    """LLMプロンプト用の警報情報文字列を生成"""
    lines = []
    for r in regions:
        for w in r.get("warnings", []):
            lines.append(f"・{r['name']}（{w['area']}）：{w['type']}（{w['status']}）")
    if not lines:
        return "現在、警報・注意報は発令されていません。"
    return "\n".join(lines)
