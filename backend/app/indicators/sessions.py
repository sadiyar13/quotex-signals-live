import datetime
from typing import Dict, Any

def evaluate_session_liquidity(now_utc: datetime.datetime = None) -> Dict[str, Any]:
    """
    Evaluates global Forex market liquidity based on major financial center session hours.
    Over 68% of global volume occurs during London & London/New York overlap.
    """
    if now_utc is None:
        now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

    hour = now_utc.hour
    minute = now_utc.minute

    # Friday market close or weekend
    weekday = now_utc.weekday()
    if weekday == 5 or (weekday == 4 and hour >= 21) or (weekday == 6 and hour < 21):
        return {
            "session_name": "تعطیلات آخر هفته",
            "is_high_liquidity": False,
            "quality_tier": "MARKET_CLOSED",
            "win_rate_multiplier": 0.0,
            "explanation": "بازار رسمی فارکس در پایان هفته تعطیل است.",
        }

    # London / New York Overlap: 12:00 - 16:00 UTC (Peak global volume)
    if 12 <= hour < 16:
        return {
            "session_name": "همپوشانی لندن و نیویورک (London-NY Overlap)",
            "is_high_liquidity": True,
            "quality_tier": "MAXIMUM",
            "win_rate_multiplier": 1.25,
            "explanation": "بالاترین سطح نقدینگی و حجم معاملات در جهان (سشن طلایی). کمترین احتمال فیک‌بریک‌اوت و خطای اسپرد.",
        }

    # London Session Alone: 07:00 - 12:00 UTC
    if 7 <= hour < 12:
        return {
            "session_name": "سشن فعال لندن (London Session)",
            "is_high_liquidity": True,
            "quality_tier": "HIGH",
            "win_rate_multiplier": 1.15,
            "explanation": "حجم نقدینگی قدرتمند بانک‌های اروپایی و بریتانیا. ایده‌آل برای جفت‌ارزهای EUR و GBP.",
        }

    # New York Afternoon: 16:00 - 21:00 UTC
    if 16 <= hour < 21:
        return {
            "session_name": "سشن نیویورک (New York Afternoon)",
            "is_high_liquidity": True,
            "quality_tier": "GOOD",
            "win_rate_multiplier": 1.05,
            "explanation": "حجم بازار آمریکا؛ مناسب برای معاملات جفت‌ارزهای دلاری.",
        }

    # Tokyo / Asian Session: 00:00 - 07:00 UTC
    if 0 <= hour < 7:
        return {
            "session_name": "سشن آسیا / توکیو (Tokyo-Asian Session)",
            "is_high_liquidity": False,
            "quality_tier": "MODERATE",
            "win_rate_multiplier": 0.95,
            "explanation": "نوسان آرام‌تر بازار؛ مناسب برای معاملات باینری روی سطوح حمایت/مقاومت جفت‌ارزهای JPY و AUD.",
        }

    # Dead / Low-volume twilight: 21:00 - 24:00 UTC
    return {
        "session_name": "ساعات کم‌حجم بین سشن‌ها (Low Volume Twilight)",
        "is_high_liquidity": False,
        "quality_tier": "LOW",
        "win_rate_multiplier": 0.75,
        "explanation": "حجم نقدینگی بسیار پایین و اسپرد متغیر؛ ریسک خطای انقضای ۵ دقیقه‌ای در این ساعات بالاتر است.",
    }
