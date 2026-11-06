import os
from calendar import monthrange
from datetime import date, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.event_labels import series_label_ids
from app.revisions import revision_reason
from app.models import Event, EventLabel, EventSeries, SeriesOccurrence
from app.time_zone import organization_today


def forward_buffer() -> timedelta:
    """How far past the Organization's today Occurrences stay materialized."""
    return timedelta(days=int(os.getenv("RECURRENCE_BUFFER_DAYS", "366")))


def materialization_horizon(time_zone: str, *, now: datetime | None = None) -> date:
    return organization_today(time_zone, now=now) + forward_buffer()


def occurrences(
    *,
    starts_on: date,
    frequency: str,
    interval: int = 1,
    until: date | None = None,
    count: int | None = None,
    last_day: bool = False,
):
    """Yield constrained iCalendar-compatible weekly/monthly/yearly dates."""
    if frequency not in {"WEEKLY", "MONTHLY", "YEARLY"} or interval < 1:
        raise ValueError("unsupported recurrence")
    generated = 0
    offset = 0
    # A last-day rule means month-end intent, so its first date is the end of
    # the starting month even when the Series starts earlier in that month.
    current = _add_months(starts_on, 0, True) if frequency == "MONTHLY" and last_day else starts_on
    while True:
        if current is not None:
            if until is not None and current > until:
                break
            yield current
            generated += 1
            if count is not None and generated >= count:
                break
        offset += 1
        if frequency == "WEEKLY":
            current = starts_on + timedelta(days=7 * interval * offset)
        elif frequency == "MONTHLY":
            current = _add_months(starts_on, offset * interval, last_day)
        else:
            current = _add_years(starts_on, offset * interval)

def to_rrule(*, starts_on: date, frequency: str, interval: int = 1, until: date | None = None, count: int | None = None, last_day: bool = False) -> str:
    """The RFC 5545 RRULE equivalent of a supported Series (ADR-0026).

    An anchored monthly day above 28 uses BYMONTHDAY with a -1 fallback, which
    RFC 5545 cannot express in one rule; it is written with the anchor and the
    fallback documented in docs/architecture/recurrence.md.
    """
    if frequency not in {"WEEKLY", "MONTHLY", "YEARLY"} or interval < 1 or (until and count) or (last_day and frequency != "MONTHLY"):
        raise ValueError("unsupported recurrence")
    parts = [f"FREQ={frequency}", f"INTERVAL={interval}"]
    if frequency == "WEEKLY":
        parts.append("BYDAY=" + ("MO", "TU", "WE", "TH", "FR", "SA", "SU")[starts_on.weekday()])
    elif frequency == "MONTHLY":
        parts.append("BYMONTHDAY=-1" if last_day else f"BYMONTHDAY={starts_on.day}")
    else:
        parts.extend([f"BYMONTH={starts_on.month}", f"BYMONTHDAY={starts_on.day}"])
    if until:
        parts.append(f"UNTIL={until.strftime('%Y%m%d')}")
    if count:
        parts.append(f"COUNT={count}")
    return ";".join(parts)


def _add_months(anchor: date, offset: int, last_day: bool) -> date:
    total = anchor.year * 12 + anchor.month - 1 + offset
    year, month = divmod(total, 12)
    month += 1
    return date(year, month, monthrange(year, month)[1] if last_day else min(anchor.day, monthrange(year, month)[1]))

def _add_years(anchor: date, offset: int) -> date | None:
    year = anchor.year + offset
    if anchor.month == 2 and anchor.day == 29 and monthrange(year, 2)[1] != 29: return None
    return date(year, anchor.month, anchor.day)


def segment_dates(series: EventSeries, *, through: date | None = None):
    """Series Dates this segment owns: its anchor's rule from ``effective_from`` on."""
    for series_date in occurrences(starts_on=series.starts_on, frequency=series.frequency, interval=series.interval, until=series.until, count=series.occurrence_count, last_day=series.last_day):
        if through is not None and series_date > through: break
        if series_date >= series.effective_from: yield series_date


def _due_dates(session: Session, series: EventSeries, through: date) -> list[date]:
    existing = set(session.scalars(select(SeriesOccurrence.series_date).where(SeriesOccurrence.series_id == series.id)).all())
    return [series_date for series_date in segment_dates(series, through=through) if series_date not in existing]


def materialize_series(session: Session, series: EventSeries, *, through: date, reason: str = "series") -> int:
    """Persist each occurrence once; safe to call repeatedly and concurrently.

    Concurrent callers serialize on the Series row, so the unique
    (series_id, series_date) constraint is never raced.
    """
    if not _due_dates(session, series, through):
        return 0
    session.execute(select(EventSeries.id).where(EventSeries.id == series.id).with_for_update())
    label_ids = series_label_ids(session, series.id)
    created = 0
    # Background materialization ("series") is not a change anyone made; creating or copying a Series passes its own reason.
    with revision_reason(session, reason):
        for series_date in _due_dates(session, series, through):
            event = Event(id=uuid4(), organization_id=series.organization_id, yearclock_id=series.yearclock_id, lane_id=series.lane_id, category_id=series.category_id, title=series.title, description=series.description, description_format=series.description_format, location=series.location, links=list(series.links or []), starts_at=series.starts_at, ends_at=series.ends_at, starts_on=series_date, ends_on=None, version=1)
            session.add(event); session.flush()
            session.add(SeriesOccurrence(id=uuid4(), series_id=series.id, organization_id=series.organization_id, series_date=series_date, event_id=event.id)); created += 1
            for label_id in label_ids:
                session.add(EventLabel(event_id=event.id, label_id=label_id, organization_id=series.organization_id))
    return created
