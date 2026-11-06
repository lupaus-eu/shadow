"""Series and Occurrence editing rules (ADR-0025, docs/architecture/recurrence.md).

An Occurrence stores only the fields a user explicitly overrode. Every other
field is read from the Series segment that owns the Occurrence's Series Date,
so later Series changes still apply where intended.
"""

from datetime import date, time, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, object_session

from app.event_labels import series_label_ids, set_series_labels, sync_event_label_ids

from app.models import Event, EventSeries, SeriesOccurrence
from app.recurrence import segment_dates

SERIES_FIELDS = ("title", "description", "description_format", "location", "links", "starts_at", "ends_at", "lane_id", "category_id")
OCCURRENCE_FIELDS = SERIES_FIELDS + ("starts_on",)
# Fields an Occurrence edit may override; Labels are synced separately from the Event columns.
OVERRIDE_FIELDS = OCCURRENCE_FIELDS + ("label_ids",)


def _encode(field: str, value: Any) -> Any:
    if value is None:
        return None
    if field == "label_ids":
        return [str(item) for item in dict.fromkeys(value)]
    if field in {"lane_id", "category_id"}:
        return str(value)
    if field == "starts_on":
        return value.isoformat()
    if field in {"starts_at", "ends_at"}:
        return value.strftime("%H:%M")
    return value


def _decode(field: str, value: Any) -> Any:
    if value is None:
        return None
    if field == "label_ids":
        return [UUID(item) for item in value]
    if field in {"lane_id", "category_id"}:
        return UUID(value)
    if field == "starts_on":
        return date.fromisoformat(value)
    if field in {"starts_at", "ends_at"}:
        return time.fromisoformat(value)
    return value


def effective_values(series: EventSeries, occurrence: SeriesOccurrence) -> dict[str, Any]:
    values = {field: getattr(series, field) for field in SERIES_FIELDS}
    values["starts_on"] = occurrence.series_date
    for field, value in (occurrence.overrides or {}).items():
        if field in OCCURRENCE_FIELDS:
            values[field] = _decode(field, value)
    return values


def effective_label_ids(session: Session, series: EventSeries, occurrence: SeriesOccurrence) -> list[UUID]:
    """An Occurrence's Labels: its override when present (possibly empty), otherwise its Series segment's."""
    overrides = occurrence.overrides or {}
    if "label_ids" in overrides:
        return _decode("label_ids", overrides["label_ids"]) or []
    return series_label_ids(session, series.id)


def apply_effective(event: Event, series: EventSeries, occurrence: SeriesOccurrence) -> bool:
    """Copy effective values and Labels onto the Occurrence's Event; True when anything changed."""
    values = effective_values(series, occurrence)
    session = object_session(event)
    changed = session is not None and sync_event_label_ids(session, event, effective_label_ids(session, series, occurrence))
    for field, value in values.items():
        if getattr(event, field) != value:
            setattr(event, field, value)
            changed = True
    if event.ends_on is not None:
        event.ends_on = None
        changed = True
    if changed:
        event.version += 1
    return changed


def override_occurrence(event: Event, series: EventSeries, occurrence: SeriesOccurrence, changes: dict[str, Any]) -> None:
    """"This occurrence only": record each changed field as an explicit override."""
    overrides = dict(occurrence.overrides or {})
    for field, value in changes.items():
        overrides[field] = _encode(field, value)
    occurrence.overrides = overrides
    if not apply_effective(event, series, occurrence):
        event.version += 1


def restore_series_values(event: Event, series: EventSeries, occurrence: SeriesOccurrence) -> None:
    occurrence.overrides = {}
    occurrence.skipped = False
    if not apply_effective(event, series, occurrence):
        event.version += 1


def _occurrences_from(session: Session, series: EventSeries, at: date) -> list[tuple[SeriesOccurrence, Event]]:
    rows = session.execute(
        select(SeriesOccurrence, Event)
        .join(Event, Event.id == SeriesOccurrence.event_id)
        .where(SeriesOccurrence.series_id == series.id, SeriesOccurrence.series_date >= at)
        .with_for_update()
    ).all()
    return [(occurrence, event) for occurrence, event in rows]


def split_series(session: Session, series: EventSeries, at: date, changes: dict[str, Any]) -> EventSeries:
    """"This and future": end the segment before ``at`` and create a successor.

    Ownership follows each Occurrence's Series Date, never an overridden
    display date. When nothing precedes ``at`` in the segment, the segment is
    edited in place instead of split.
    """
    first = next(segment_dates(series), None)
    if first is None or at <= first:
        label_ids = changes.pop("label_ids", None)
        if label_ids is not None:
            set_series_labels(session, series, label_ids)
        for field, value in changes.items():
            setattr(series, field, value)
        series.version += 1
        for occurrence, event in _occurrences_from(session, series, series.effective_from):
            apply_effective(event, series, occurrence)
        return series

    label_ids = changes.pop("label_ids", None)
    successor = EventSeries(
        id=uuid4(),
        organization_id=series.organization_id,
        yearclock_id=series.yearclock_id,
        lane_id=changes.get("lane_id", series.lane_id),
        category_id=changes.get("category_id", series.category_id),
        title=changes.get("title", series.title),
        description=changes.get("description", series.description),
        description_format=changes.get("description_format") or series.description_format,
        location=changes.get("location", series.location),
        links=changes.get("links", series.links),
        starts_at=changes["starts_at"] if "starts_at" in changes else series.starts_at,
        ends_at=changes["ends_at"] if "ends_at" in changes else series.ends_at,
        starts_on=series.starts_on,
        effective_from=at,
        frequency=series.frequency,
        interval=series.interval,
        until=series.until,
        occurrence_count=series.occurrence_count,
        last_day=series.last_day,
        version=1,
    )
    session.add(successor)
    session.flush()
    set_series_labels(session, successor, series_label_ids(session, series.id) if label_ids is None else label_ids)
    series.until = at - timedelta(days=1)
    series.version += 1
    for occurrence, event in _occurrences_from(session, series, at):
        occurrence.series_id = successor.id
        apply_effective(event, successor, occurrence)
    return successor


def end_series(session: Session, series: EventSeries, at: date) -> int:
    """Remove the segment's Occurrences from ``at`` on; earlier history stays."""
    removed = _occurrences_from(session, series, at)
    for _occurrence, event in removed:
        session.delete(event)
    series.until = at - timedelta(days=1)
    series.version += 1
    return len(removed)
