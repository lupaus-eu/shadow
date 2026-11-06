"""Operational ceilings (docs/architecture/operational-limits.md).

Creation beyond a ceiling fails with 409 and a machine-readable reason, so
dense Yearclocks never degrade silently. Each ceiling is configurable; the
parent row is locked while counting so concurrent requests cannot overshoot.
"""

import os
from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Category, Event, EventSeries, Label, Lane, Organization, Yearclock


@dataclass(frozen=True)
class Ceiling:
    name: str
    variable: str
    default: int

    @property
    def maximum(self) -> int:
        return int(os.getenv(self.variable, str(self.default)))


YEARCLOCKS = Ceiling("yearclocks_per_organization", "LIMIT_YEARCLOCKS_PER_ORGANIZATION", 50)
LANES = Ceiling("lanes_per_yearclock", "LIMIT_LANES_PER_YEARCLOCK", 12)
CATEGORIES = Ceiling("categories_per_yearclock", "LIMIT_CATEGORIES_PER_YEARCLOCK", 40)
EVENTS = Ceiling("events_per_yearclock", "LIMIT_EVENTS_PER_YEARCLOCK", 3000)
SERIES = Ceiling("series_per_yearclock", "LIMIT_SERIES_PER_YEARCLOCK", 100)
LABELS = Ceiling("labels_per_organization", "LIMIT_LABELS_PER_ORGANIZATION", 200)
LABELS_PER_EVENT = Ceiling("labels_per_event", "LIMIT_LABELS_PER_EVENT", 10)
ORGANIZATION_CATEGORIES = Ceiling("organization_categories", "LIMIT_ORGANIZATION_CATEGORIES", 40)
BULK_EVENTS = Ceiling("bulk_events", "LIMIT_BULK_EVENTS", 200)
GROUPS = Ceiling("groups_per_organization", "LIMIT_GROUPS_PER_ORGANIZATION", 100)
# Exports and imports per user and hour (Yearclock V2 P7), counted from the Audit Log.
BILLING_CONTACT_CHANGES = Ceiling("billing_contact_changes_per_day", "LIMIT_BILLING_CONTACT_CHANGES_PER_DAY", 5)
EXPORTS_PER_HOUR = Ceiling("exports_per_hour", "LIMIT_EXPORTS_PER_HOUR", 20)
ORGANIZATION_EXPORTS_PER_HOUR = Ceiling("organization_exports_per_hour", "LIMIT_ORGANIZATION_EXPORTS_PER_HOUR", 3)
CEILINGS = (YEARCLOCKS, LANES, CATEGORIES, EVENTS, SERIES, LABELS, LABELS_PER_EVENT, ORGANIZATION_CATEGORIES, BULK_EVENTS, GROUPS)


def _refuse_at(ceiling: Ceiling, count: int) -> None:
    if count >= ceiling.maximum:
        raise HTTPException(status_code=409, detail={"reason": "limit_reached", "limit": ceiling.name, "maximum": ceiling.maximum})


def require_yearclock_capacity(session: Session, organization_id: UUID) -> None:
    session.execute(select(Organization.id).where(Organization.id == organization_id).with_for_update())
    _refuse_at(YEARCLOCKS, session.scalar(select(func.count()).select_from(Yearclock).where(Yearclock.organization_id == organization_id, Yearclock.deleted_at.is_(None))))


def _lock_yearclock(session: Session, yearclock_id: UUID) -> None:
    session.execute(select(Yearclock.id).where(Yearclock.id == yearclock_id).with_for_update())


def require_lane_capacity(session: Session, yearclock_id: UUID) -> None:
    _lock_yearclock(session, yearclock_id)
    _refuse_at(LANES, session.scalar(select(func.count()).select_from(Lane).where(Lane.yearclock_id == yearclock_id)))


def require_category_capacity(session: Session, yearclock_id: UUID) -> None:
    _lock_yearclock(session, yearclock_id)
    _refuse_at(CATEGORIES, session.scalar(select(func.count()).select_from(Category).where(Category.yearclock_id == yearclock_id)))


def require_event_capacity(session: Session, yearclock_id: UUID) -> None:
    _lock_yearclock(session, yearclock_id)
    _refuse_at(EVENTS, session.scalar(select(func.count()).select_from(Event).where(Event.yearclock_id == yearclock_id, Event.deleted_at.is_(None))))


def require_series_capacity(session: Session, yearclock_id: UUID) -> None:
    require_event_capacity(session, yearclock_id)
    _refuse_at(SERIES, session.scalar(select(func.count()).select_from(EventSeries).where(EventSeries.yearclock_id == yearclock_id)))


def require_label_capacity(session: Session, organization_id: UUID) -> None:
    session.execute(select(Organization.id).where(Organization.id == organization_id).with_for_update())
    _refuse_at(LABELS, session.scalar(select(func.count()).select_from(Label).where(Label.organization_id == organization_id)))


def require_organization_category_capacity(session: Session, organization_id: UUID) -> None:
    session.execute(select(Organization.id).where(Organization.id == organization_id).with_for_update())
    _refuse_at(ORGANIZATION_CATEGORIES, session.scalar(select(func.count()).select_from(Category).where(Category.organization_id == organization_id, Category.yearclock_id.is_(None))))


def require_bulk_size(count: int) -> None:
    if count > BULK_EVENTS.maximum:
        raise HTTPException(status_code=409, detail={"reason": "limit_reached", "limit": BULK_EVENTS.name, "maximum": BULK_EVENTS.maximum})


def require_group_capacity(session: Session, organization_id: UUID) -> None:
    from app.models import Group

    session.execute(select(Organization.id).where(Organization.id == organization_id).with_for_update())
    _refuse_at(GROUPS, session.scalar(select(func.count()).select_from(Group).where(Group.organization_id == organization_id)))

