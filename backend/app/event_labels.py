"""Label assignments on Events (Yearclock V2, P2 ticket 03)."""

from collections import defaultdict
from collections.abc import Iterable
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import Uuid, delete, func, literal, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.limits import LABELS_PER_EVENT
from app.models import Event, EventLabel, EventSeries, Label, SeriesLabel, SeriesOccurrence


def resolve_labels(session: Session, organization_id: UUID, label_ids: Iterable[UUID]) -> list[Label]:
    """The requested Labels, refused when there are too many, duplicates, or Labels of another Organization."""
    requested = list(label_ids)
    if len(set(requested)) != len(requested):
        raise HTTPException(status_code=422, detail="label_ids must be unique")
    if len(requested) > LABELS_PER_EVENT.maximum:
        raise HTTPException(status_code=409, detail={"reason": "limit_reached", "limit": LABELS_PER_EVENT.name, "maximum": LABELS_PER_EVENT.maximum})
    labels = session.scalars(select(Label).where(Label.organization_id == organization_id, Label.id.in_(requested))).all() if requested else []
    if len(labels) != len(requested):
        raise HTTPException(status_code=422, detail="label_ids must be Labels of this Organization")
    order = {label_id: index for index, label_id in enumerate(requested)}
    return sorted(labels, key=lambda label: order[label.id])


def event_label_ids(session: Session, event_ids: Iterable[UUID]) -> dict[UUID, list[UUID]]:
    ids = list(event_ids)
    result: dict[UUID, list[UUID]] = defaultdict(list)
    if not ids:
        return result
    rows = session.execute(
        select(EventLabel.event_id, EventLabel.label_id)
        .join(Label, Label.id == EventLabel.label_id)
        .where(EventLabel.event_id.in_(ids))
        .order_by(func.lower(Label.name))
    ).all()
    for event_id, label_id in rows:
        result[event_id].append(label_id)
    return result


def set_event_labels(session: Session, event: Event, labels: list[Label]) -> dict[str, list[str]]:
    """Replace the Event's Labels and return the added and removed names for the audit summary."""
    session.flush()
    current = {label.id: label for label in session.scalars(select(Label).join(EventLabel, EventLabel.label_id == Label.id).where(EventLabel.event_id == event.id)).all()}
    wanted = {label.id: label for label in labels}
    removed = [current[label_id].name for label_id in current.keys() - wanted.keys()]
    added = [wanted[label_id].name for label_id in wanted.keys() - current.keys()]
    if removed:
        session.execute(delete(EventLabel).where(EventLabel.event_id == event.id, EventLabel.label_id.in_(current.keys() - wanted.keys())))
    for label_id in wanted.keys() - current.keys():
        session.add(EventLabel(event_id=event.id, label_id=label_id, organization_id=event.organization_id))
    return {"labels_added": sorted(added), "labels_removed": sorted(removed)}


def label_usage(session: Session, organization_id: UUID) -> dict[UUID, int]:
    """How many Events carry each Label, including deleted Events that can still be restored."""
    rows = session.execute(select(EventLabel.label_id, func.count()).where(EventLabel.organization_id == organization_id).group_by(EventLabel.label_id)).all()
    return {label_id: count for label_id, count in rows}


def move_label_assignments(session: Session, source_id: UUID, target_id: UUID) -> None:
    """Re-point every Event, Series, and Occurrence override from one Label to another, never duplicating one."""
    for model, owner in ((EventLabel, EventLabel.event_id), (SeriesLabel, SeriesLabel.series_id)):
        moved = select(owner, literal(target_id, type_=Uuid), model.organization_id).where(model.label_id == source_id)
        session.execute(
            insert(model)
            .from_select([owner.key, "label_id", "organization_id"], moved)
            .on_conflict_do_nothing(index_elements=[owner.key, "label_id"])
        )
        session.execute(delete(model).where(model.label_id == source_id))
    rewrite_override_labels(session, source_id, target_id)


def rewrite_override_labels(session: Session, source_id: UUID, target_id: UUID | None) -> None:
    """Replace (merge) or drop (delete) a Label inside Occurrence overrides."""
    source, target = str(source_id), str(target_id) if target_id else None
    for occurrence in session.scalars(select(SeriesOccurrence).where(SeriesOccurrence.overrides.has_key("label_ids")).with_for_update()).all():
        current = list(occurrence.overrides.get("label_ids") or [])
        if source not in current:
            continue
        replaced = [target if value == source else value for value in current if target or value != source]
        occurrence.overrides = {**occurrence.overrides, "label_ids": list(dict.fromkeys(item for item in replaced if item))}


def series_label_ids(session: Session, series_id: UUID) -> list[UUID]:
    return list(session.scalars(select(SeriesLabel.label_id).join(Label, Label.id == SeriesLabel.label_id).where(SeriesLabel.series_id == series_id).order_by(func.lower(Label.name))).all())


def set_series_labels(session: Session, series: EventSeries, label_ids: Iterable[UUID]) -> None:
    session.flush()
    session.execute(delete(SeriesLabel).where(SeriesLabel.series_id == series.id))
    for label_id in dict.fromkeys(label_ids):
        session.add(SeriesLabel(series_id=series.id, label_id=label_id, organization_id=series.organization_id))
    session.flush()


def sync_event_label_ids(session: Session, event: Event, label_ids: Iterable[UUID]) -> bool:
    """Make the Event carry exactly these Labels (used for Occurrence Events); True when anything changed."""
    session.flush()
    wanted = set(label_ids)
    current = set(session.scalars(select(EventLabel.label_id).where(EventLabel.event_id == event.id)).all())
    if wanted == current:
        return False
    if current - wanted:
        session.execute(delete(EventLabel).where(EventLabel.event_id == event.id, EventLabel.label_id.in_(current - wanted)))
    for label_id in wanted - current:
        session.add(EventLabel(event_id=event.id, label_id=label_id, organization_id=event.organization_id))
    return True


def touch_events_with_label(session: Session, label_id: UUID) -> None:
    """Advance the version of every Event carrying the Label, so open editors see the change."""
    session.execute(update(Event).where(Event.id.in_(select(EventLabel.event_id).where(EventLabel.label_id == label_id))).values(version=Event.version + 1))
