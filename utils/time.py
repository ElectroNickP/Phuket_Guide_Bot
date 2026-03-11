import datetime
import zoneinfo

PHUKET_TZ = zoneinfo.ZoneInfo("Asia/Bangkok")

def get_phuket_now() -> datetime.datetime:
    """Returns the current datetime in Phuket timezone (UTC+7)."""
    return datetime.datetime.now(PHUKET_TZ)

def get_phuket_today() -> datetime.date:
    """Returns the current date in Phuket timezone."""
    return get_phuket_now().date()
