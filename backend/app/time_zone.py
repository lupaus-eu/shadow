from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo


def organization_today(time_zone: str, *, now: datetime | None = None) -> date:
    """Return the current all-day date in an Organization's IANA time zone."""
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(ZoneInfo(time_zone)).date()
