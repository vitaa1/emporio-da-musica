"""Resolve declared receipt dates against an explicitly supplied store clock."""

import re
from collections.abc import Callable
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

Clock = Callable[[], datetime]
STORE_TIMEZONE = "America/Campo_Grande"


def store_today(clock: Clock) -> date:
    now = clock()
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Clock must return a timezone-aware datetime")
    return now.astimezone(ZoneInfo(STORE_TIMEZONE)).date()


def resolve_receipt_date(value: str, today: date) -> date:
    relative = {"today": 0, "yesterday": 1, "day_before_yesterday": 2}
    if value in relative:
        result = today - timedelta(days=relative[value])
    elif re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        result = date.fromisoformat(value)
    else:
        raise ValueError("An unambiguous receipt date is required")
    if result > today:
        raise ValueError("Receipt date cannot be in the future")
    return result
