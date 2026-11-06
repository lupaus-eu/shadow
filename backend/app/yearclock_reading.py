"""The single read check for content of other Yearclocks (Yearclock V2, P3).

Copying and Linked Lanes never widen access: a user reaches another
Yearclock's Lane only when this check lets them read that Yearclock. The
check runs on every read with the viewer's own access.
"""
from typing import Iterable, Literal
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from app.access import accessible_yearclock_ids, membership_of
from app.models import Lane, Yearclock


class LinkSource(BaseModel):
    """What a viewer may know about a Linked Lane's source."""
    available: bool
    reason: Literal["no_access", "deleted"] | None = None
    yearclock_id: UUID | None = None
    yearclock_name: str | None = None
    lane_name: str | None = None


def readable_yearclock_ids(session: Session, organization_id: UUID, user_account_id: UUID, *, include_deleted: bool = False) -> set[UUID]:
    """Yearclocks of the Organization that the user may read, by the single access rule (``app.access``)."""
    membership = membership_of(session, organization_id, user_account_id)
    return accessible_yearclock_ids(session, membership, include_deleted=include_deleted) if membership else set()


def link_sources(session: Session, organization_id: UUID, user_account_id: UUID, lanes: Iterable[Lane]) -> dict[UUID, LinkSource]:
    """The source of each Linked Lane as this viewer may see it."""
    linked = {lane.id: lane.source_lane_id for lane in lanes if lane.source_lane_id is not None}
    if not linked:
        return {}
    rows = {lane.id: (lane, clock) for lane, clock in session.execute(select(Lane, Yearclock).join(Yearclock, Yearclock.id == Lane.yearclock_id).where(Lane.id.in_(set(linked.values())))).all()}
    readable = readable_yearclock_ids(session, organization_id, user_account_id, include_deleted=True)
    result: dict[UUID, LinkSource] = {}
    for lane_id, source_id in linked.items():
        source, clock = rows.get(source_id, (None, None))
        if source is None or clock.id not in readable:
            result[lane_id] = LinkSource(available=False, reason="no_access")
        elif clock.deleted_at is not None:
            result[lane_id] = LinkSource(available=False, reason="deleted", yearclock_id=clock.id, yearclock_name=clock.name)
        else:
            result[lane_id] = LinkSource(available=True, yearclock_id=clock.id, yearclock_name=clock.name, lane_name=source.name)
    return result


def readable_links(session: Session, organization_id: UUID, yearclock_id: UUID, user_account_id: UUID) -> dict[UUID, tuple[UUID, UUID]]:
    """Source Lane id -> (Linked Lane id, source Yearclock id) for the links of a Yearclock this viewer may read."""
    source = aliased(Lane)
    rows = session.execute(select(Lane.id, source.id, source.yearclock_id).join(source, source.id == Lane.source_lane_id).where(Lane.yearclock_id == yearclock_id, Lane.organization_id == organization_id)).all()
    if not rows:
        return {}
    readable = readable_yearclock_ids(session, organization_id, user_account_id)
    return {source_id: (lane_id, source_clock) for lane_id, source_id, source_clock in rows if source_clock in readable}
