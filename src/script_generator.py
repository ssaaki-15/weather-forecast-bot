"""
② 原稿生成モジュール（Claude API / Haiku）
- 気象データをNHKスタイルのニュース原稿にリライト
- claude-haiku-4-5 を使用（低コスト・高速）
"""

import logging
import os
from datetime import datetime, timezone, timedelta

import anthropic

from config import SCRIPT_CONFIG, NHK_PROMPT_TEMPLATE, WEEKDAY_JA

logger = logging.getLogger(__name__)
JST = timezone(timedelta(hours=9))


def generate_script(
    national_overview: str,
    region_data_str: str,
    warnings_str: str,
    target_datetime: datetime | None = None,
) -> str:
    """
    Claude API で天気予報原稿を生成する

    Args:
        national_overview:  気象庁の全国概況テキスト
        region_data_str:    地域別気象データ（整形済み文字列）
        warnings_str:       警報・注意報情報（整形済み文字列）
        target_datetime:    放送日時（デフォルト：現在時刻）

    Returns:
        NHKスタイルの天気予報原稿（str）
    """
    if target_datetime is None:
        target_datetime = datetime.now(JST)

    weekday = WEEKDAY_JA[target_datetime.weekday()]
    dt_str = target_datetime.strftime(f"%Y年%m月%d日（{weekday}）午前7時")

    prompt = NHK_PROMPT_TEMPLATE.format(
        datetime=dt_str,
        national_overview=national_overview,
        region_data=region_data_str,
        warnings=warnings_str,
        target_chars=SCRIPT_CONFIG["target_chars"],
    )

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    logger.info(f"原稿生成中（モデル: {SCRIPT_CONFIG['model']}）...")
    try:
        message = client.messages.create(
            model=SCRIPT_CONFIG["model"],
            max_tokens=SCRIPT_CONFIG["max_tokens"],
            messages=[{"role": "user", "content": prompt}],
        )
        script = message.content[0].text.strip()
        logger.info(f"原稿生成完了（{len(script)}文字）")

        # 入力/出力トークン数をログ出力（コスト把握）
        usage = message.usage
        logger.info(
            f"Token usage — input: {usage.input_tokens}, "
            f"output: {usage.output_tokens}"
        )
        return script

    except anthropic.APIError as e:
        logger.error(f"Claude API エラー: {e}")
        return _fallback_script(target_datetime, region_data_str)


def _fallback_script(dt: datetime, region_data_str: str) -> str:
    """API失敗時のフォールバック原稿（データをそのまま読み上げ）"""
    weekday = WEEKDAY_JA[dt.weekday()]
    date_str = dt.strftime(f"%m月%d日（{weekday}）")
    return (
        f"おはようございます。{date_str}の天気をお伝えします。"
        f"本日の全国の天気はご覧のとおりです。"
        f"詳しくは気象庁のホームページをご確認ください。"
        f"引き続きお気をつけてお過ごしください。"
    )


def split_script_by_region(script: str, region_names: list[str]) -> dict[str, str]:
    """
    原稿を地域ごとに分割する（字幕生成用）

    各地方の名前を目印に文章を分割。
    正確な分割が難しい場合は全文を各地域に割り当て。
    """
    segments = {}
    lines = script.split("。")

    for region_name in region_names:
        matched = []
        for line in lines:
            if region_name in line or "全国" in line:
                matched.append(line + "。")
        segments[region_name] = "".join(matched) if matched else script

    return segments
