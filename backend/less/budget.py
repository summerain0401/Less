from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select

from less.config import settings
from less.models import NormalizeRun, now


def day_bounds(day: date):
    tz = ZoneInfo(settings().timezone)
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def local_today(at=None):
    return (at or now()).astimezone(ZoneInfo(settings().timezone)).date()


def daily_usage(db, day: date):
    start, end = day_bounds(day)
    known, legacy = 0, 0
    for started, count, logs in db.execute(
        select(NormalizeRun.started_at, NormalizeRun.attempts, NormalizeRun.attempts_log)
    ):
        for entry in logs:
            timestamp = datetime.fromisoformat(entry["started_at"])
            if start <= timestamp < end:
                known += 1
        if started and start <= started < end:
            # Legacy records lack attempt timestamps: count conservatively, disclose the estimate.
            legacy += max(0, count - len(logs))
    used = known + legacy
    return {
        "limit": settings().ai_daily_limit,
        "used": used,
        "remaining": max(0, settings().ai_daily_limit - used),
        "legacy_estimated": legacy,
        "resets_at": end,
    }
