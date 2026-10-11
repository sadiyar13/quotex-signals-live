import datetime
from typing import Dict, Any, Tuple

# Standard Forex trading hours (UTC):
# Opens Sunday ~21:00 UTC (Sydney session start)
# Closes Friday ~21:00 UTC (New York session close)
# Closed all day Saturday and Sunday prior to 21:00 UTC

ALLOWED_FOREX_SYMBOLS = [
    "EUR/USD",
    "GBP/USD",
    "USD/JPY",
    "AUD/USD",
    "USD/CHF",
    "USD/CAD",
    "NZD/USD",
]

def is_otc_symbol(symbol: str) -> bool:
    """Detects and rejects OTC / synthetic broker symbols."""
    sym_upper = symbol.upper()
    return "OTC" in sym_upper or "_OTC" in sym_upper or "-OTC" in sym_upper

def get_forex_market_status(now_utc: datetime.datetime = None) -> Dict[str, Any]:
    """
    Evaluates whether the global official Forex market is currently open.
    Returns market status, current session info, and next open/close estimates.
    """
    if now_utc is None:
        now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

    weekday = now_utc.weekday()  # Monday is 0, Sunday is 6
    hour = now_utc.hour
    minute = now_utc.minute

    # Friday after 21:00 UTC -> Market closes for the weekend
    if weekday == 4 and (hour > 21 or (hour == 21 and minute >= 0)):
        is_open = False
        reason = "بازار رسمی فارکس در پایان جلسه نیویورک در روز جمعه بسته شده است."
    # Saturday -> Closed all day
    elif weekday == 5:
        is_open = False
        reason = "بازار رسمی فارکس در روز شنبه تعطیل است."
    # Sunday before 21:00 UTC -> Closed until Sydney open
    elif weekday == 6 and hour < 21:
        is_open = False
        hours_left = 21 - hour
        reason = f"بازار رسمی فارکس تا زمان بازگشایی جلسه سیدنی در ساعت ۲۱:۰۰ UTC (حدود {hours_left} ساعت دیگر) بسته است."
    else:
        is_open = True
        reason = "بازار رسمی فارکس باز و در حال معامله فعال بین‌بانکی است."

    # Identify current major active trading sessions
    active_sessions = []
    if is_open:
        # Sydney: 21:00 - 06:00 UTC
        if hour >= 21 or hour < 6:
            active_sessions.append("سیدنی (Sydney)")
        # Tokyo: 00:00 - 09:00 UTC
        if 0 <= hour < 9:
            active_sessions.append("توکیو (Tokyo)")
        # London: 07:00 - 16:00 UTC
        if 7 <= hour < 16:
            active_sessions.append("لندن (London)")
        # New York: 12:00 - 21:00 UTC
        if 12 <= hour < 21:
            active_sessions.append("نیویورک (New York)")

    return {
        "is_open": is_open,
        "utc_time": now_utc.isoformat(),
        "weekday": weekday,
        "active_sessions": active_sessions if is_open else [],
        "reason": reason,
        "otc_warning": "توجه: نمادهای OTC به دلیل قیمت‌گذاری غیررسمی توسط این سامانه پشتیبانی نمی‌شوند.",
    }
