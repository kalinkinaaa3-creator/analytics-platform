"""Creation-date windows for the weekly CRM reconciliation."""
from calendar import monthrange
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def reconciliation_windows(boundary_date, *, lead_days=14, deal_months=4):
    if lead_days < 1 or deal_months < 1:
        raise ValueError("--days and --deals-months must be positive integers.")
    year, month_index = divmod(boundary_date.year * 12 + boundary_date.month - 1 - deal_months, 12)
    if year < 1:
        raise ValueError("--deals-months exceeds the supported calendar range.")
    month = month_index + 1
    deal_date = boundary_date.replace(year=year, month=month,
        day=min(boundary_date.day, monthrange(year, month)[1]))
    end = datetime.combine(boundary_date, time.min, tzinfo=MOSCOW_TZ)
    return end - timedelta(days=lead_days), datetime.combine(deal_date, time.min, tzinfo=MOSCOW_TZ), end
