import datetime
import zoneinfo

PHUKET_TZ = zoneinfo.ZoneInfo("Asia/Bangkok")

def get_phuket_now() -> datetime.datetime:
    """Returns the current datetime in Phuket timezone (UTC+7)."""
    return datetime.datetime.now(PHUKET_TZ)

def get_phuket_today() -> datetime.date:
    """Returns the current date in Phuket timezone."""
    return get_phuket_now().date()

def is_time_format(s: str) -> bool:
    """Checks if a string is in HH:MM format."""
    if not s:
        return False
    import re
    return bool(re.match(r'^\d{1,2}:\d{2}$', s.strip()))
