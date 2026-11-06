"""Event Revisions: the state of an Event after every change (Yearclock V2, P4).

Revisions are written by session hooks, so no Event-changing path can forget
them. After each flush the hooks note which Events were created or changed
and why (the reason set with ``revision_reason``). Before the commit they
store one revision per Event whose state differs from its latest revision.
Changes made with bulk SQL statements are reported with ``mark_changed``.
Revisions are customer content kept outside the Audit Log (ADR-0014).
"""

import os
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, event as sa_event, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.audit import current_source
from app.event_content import links_json, parse_stored_links, time_text
from app.models import Event, EventLabel, EventRevision, SeriesOccurrence

SNAPSHOT_FIELDS = ("title", "starts_on", "ends_on", "lane_id", "category_id", "label_ids", "description", "description_format", "location", "links", "starts_at", "ends_at", "deleted", "skipped")
_PENDING = "revision_pending"
_REASON = "revision_reason"


def revisions_per_event() -> int:
    """How many revisions are kept per Event (``LIMIT_REVISIONS_PER_EVENT``); older ones are pruned."""
    return int(os.getenv("LIMIT_REVISIONS_PER_EVENT", "100"))


@contextmanager
def revision_reason(session: Session, reason: str, detail: dict[str, Any] | None = None) -> Iterator[None]:
    """Attribute the Event changes flushed inside the block to ``reason``."""
    previous = session.info.get(_REASON)
    session.flush()
    session.info[_REASON] = (reason, detail or {})
    try:
        yield
        session.flush()
    finally:
        session.info[_REASON] = previous


def set_revision_reason(session: Session, reason: str, detail: dict[str, Any] | None = None) -> None:
    """Attribute the remaining Event changes of this transaction to ``reason``."""
    session.info[_REASON] = (reason, detail or {})


def mark_changed(session: Session, event_ids: Iterable[UUID], reason: str | None = None, detail: dict[str, Any] | None = None) -> None:
    """Report Events changed by bulk SQL, which the flush hook cannot see."""
    pending = session.info.setdefault(_PENDING, {})
    current = (reason, detail or {}) if reason else session.info.get(_REASON) or ("edit", {})
    for event_id in event_ids:
        pending.setdefault(event_id, current)


def _source_reason() -> tuple[str, dict[str, Any]] | None:
    """Changes made through the MCP interface say so in their history (ADR-0037)."""
    source = current_source()
    return ("mcp", {"client": source.get("mcp_client")}) if source and source.get("source") == "mcp" else None


def _collect(session: Session, _context: Any) -> None:
    reason = session.info.get(_REASON) or _source_reason() or ("edit", {})
    pending = session.info.setdefault(_PENDING, {})
    for item in list(session.new) + list(session.dirty):
        if isinstance(item, Event) and (item in session.new or session.is_modified(item, include_collections=False)):
            pending.setdefault(item.id, reason)


def snapshot_of(session: Session, events: list[Event]) -> dict[UUID, dict[str, Any]]:
    ids = [item.id for item in events]
    labels: dict[UUID, list[str]] = {item: [] for item in ids}
    for event_id, label_id in session.execute(select(EventLabel.event_id, EventLabel.label_id).where(EventLabel.event_id.in_(ids))).all():
        labels[event_id].append(str(label_id))
    occurrences = dict(session.execute(select(SeriesOccurrence.event_id, SeriesOccurrence.skipped).where(SeriesOccurrence.event_id.in_(ids))).all())
    return {
        item.id: {
            "title": item.title,
            "starts_on": item.starts_on.isoformat(),
            "ends_on": item.ends_on.isoformat() if item.ends_on else None,
            "lane_id": str(item.lane_id),
            "category_id": str(item.category_id) if item.category_id else None,
            "label_ids": sorted(labels[item.id]),
            "description": item.description,
            "description_format": item.description_format,
            "location": item.location,
            "links": links_json(item.links),
            "starts_at": time_text(item.starts_at),
            "ends_at": time_text(item.ends_at),
            "deleted": item.deleted_at is not None,
            "skipped": bool(occurrences.get(item.id, False)),
        }
        for item in events
    }


def _normalize(snapshot: dict[str, Any]) -> dict[str, Any]:
    """A snapshot in the current shape: an entry written before P11 holds ``external_url``, which reads as a link list."""
    values = {field: (sorted(snapshot.get(field) or []) if field == "label_ids" else snapshot.get(field)) for field in SNAPSHOT_FIELDS}
    values["description_format"] = snapshot.get("description_format") or "plain"
    values["links"] = parse_stored_links(snapshot["links"] if "links" in snapshot else snapshot.get("external_url"))
    return values


def _actor(session: Session) -> tuple[UUID | None, str]:
    account, support = session.execute(text("SELECT NULLIF(current_setting('app.current_user_account_id', true), ''), NULLIF(current_setting('app.current_support_access_id', true), '')")).one()
    if support:
        return (UUID(account) if account else None), "support"
    return (UUID(account), "member") if account else (None, "system")


def _write(session: Session) -> None:
    if session.info.get("revision_writing"):
        return
    # before_commit runs before the commit's own flush, so flush first to collect the last changes.
    session.flush()
    if not session.info.get(_PENDING):
        return
    session.info["revision_writing"] = True
    try:
        pending: dict[UUID, tuple[str, dict]] = dict(session.info.pop(_PENDING, {}) or {})
        events = session.scalars(select(Event).where(Event.id.in_(pending.keys()))).all()
        if not events:
            return
        latest = {
            row.event_id: row
            for row in session.scalars(
                select(EventRevision).where(EventRevision.event_id.in_([item.id for item in events])).order_by(EventRevision.event_id, EventRevision.created_at.desc(), EventRevision.id.desc()).distinct(EventRevision.event_id)
            ).all()
        }
        series = dict(session.execute(select(SeriesOccurrence.event_id, SeriesOccurrence.series_id).where(SeriesOccurrence.event_id.in_([item.id for item in events]))).all())
        snapshots = snapshot_of(session, list(events))
        account, actor_kind = _actor(session)
        written = []
        for item in events:
            reason, detail = pending[item.id]
            after, before = snapshots[item.id], latest.get(item.id)
            previous = _normalize(before.snapshot) if before else None
            changed = [field for field in SNAPSHOT_FIELDS if previous is None or previous[field] != after[field]]
            if previous is not None and not changed:
                continue
            if previous is None: kind = "created"
            elif reason == "restore": kind = "version_restored"
            elif after["deleted"] and not previous["deleted"]: kind = "deleted"
            elif previous["deleted"] and not after["deleted"]: kind = "restored"
            else: kind = "updated"
            session.add(EventRevision(id=uuid4(), organization_id=item.organization_id, yearclock_id=item.yearclock_id, event_id=item.id, series_id=series.get(item.id), kind=kind, reason=reason, reason_detail=detail, actor_account_id=account, actor_kind=actor_kind, snapshot=after, changed_fields=[] if previous is None else changed))
            written.append(item.id)
        session.flush()
        _prune(session, written)
    finally:
        session.info.pop("revision_writing", None)


def _prune(session: Session, event_ids: list[UUID]) -> None:
    keep = revisions_per_event()
    for event_id in event_ids:
        if (session.scalar(select(func.count()).select_from(EventRevision).where(EventRevision.event_id == event_id)) or 0) <= keep:
            continue
        kept = select(EventRevision.id).where(EventRevision.event_id == event_id).order_by(EventRevision.created_at.desc(), EventRevision.id.desc()).limit(keep)
        session.execute(delete(EventRevision).where(EventRevision.event_id == event_id, EventRevision.id.not_in(kept)))


def write_pending(session: Session) -> None:
    """Write the Event Revisions of the changes flushed so far, under the current request context (bulk work that switches Organizations)."""
    _write(session)


def _discard(session: Session, *_args: Any) -> None:
    session.info.pop(_PENDING, None)
    session.info.pop(_REASON, None)


def install_revision_hooks(factory: sessionmaker[Session]) -> None:
    """Record revisions for every session made by ``factory``."""
    if getattr(factory, "_revision_hooks", False):
        return
    sa_event.listen(factory, "after_flush", _collect)
    sa_event.listen(factory, "before_commit", _write)
    sa_event.listen(factory, "after_rollback", _discard)
    sa_event.listen(factory, "after_commit", _discard)
    factory._revision_hooks = True  # type: ignore[attr-defined]
