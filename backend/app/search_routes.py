"""Search one Yearclock across all time (Yearclock V2, P2 ticket 07).

Matching ignores case and accents (Unicode NFKD without combining marks, then
casefold) and looks in titles, descriptions, locations, link titles, Category names, and Label names.
It runs in Python over the Yearclock's Events, which the Event ceiling bounds,
so no PostgreSQL extension is needed. Recurring Occurrences are found as far as
they are materialized (the forward buffer). Events of Linked Lanes are found
when the viewer may read their source Yearclock. Searches are not audited.
"""

import unicodedata
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.auth import AuthenticatedUser
from app.auth_routes import AuthenticatedUserDependency
from app.event_labels import event_label_ids
from app.event_routes import EventResponse, _access_session, _response
from app.rich_text import plain_text
from app.models import Category, Event, Label, SeriesOccurrence
from app.yearclock_reading import readable_links

PAGE_SIZE = 50
MIN_QUERY = 2


def normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(char for char in decomposed if not unicodedata.combining(char)).casefold()


class SearchResponse(BaseModel):
    items: list[EventResponse]
    next_offset: int | None
    total: int
    includes_recurring: bool


def create_search_router(*, session_factory: sessionmaker[Session], authenticated_user_dependency: AuthenticatedUserDependency) -> APIRouter:
    router = APIRouter(prefix="/api/v1/organizations", tags=["Search"])

    @router.get("/{organization_id}/yearclocks/{yearclock_id}/search", response_model=SearchResponse)
    def search(organization_id: UUID, yearclock_id: UUID, q: str = Query(max_length=200), offset: int = Query(default=0, ge=0), user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> SearchResponse:
        return search_events(session_factory, organization_id, yearclock_id, user, q, offset)
    return router


def search_events(session_factory: sessionmaker[Session], organization_id: UUID, yearclock_id: UUID, user: AuthenticatedUser, q: str, offset: int) -> SearchResponse:
    needle = normalize(" ".join(q.split()))
    if len(needle) < MIN_QUERY:
        raise HTTPException(status_code=422, detail=f"search text needs at least {MIN_QUERY} characters")
    with _access_session(session_factory, organization_id, yearclock_id, user, mutate=False) as session:
        links = readable_links(session, organization_id, yearclock_id, user.account.id)
        events = session.scalars(select(Event).where(or_(Event.yearclock_id == yearclock_id, Event.lane_id.in_(links.keys())), Event.deleted_at.is_(None)).order_by(Event.starts_on, Event.id)).all()
        occurrences = {item.event_id: item for item in session.scalars(select(SeriesOccurrence).where(SeriesOccurrence.event_id.in_([event.id for event in events]))).all()}
        categories = {item.id: normalize(item.name) for item in session.scalars(select(Category).where(Category.organization_id == organization_id)).all()}
        labels = {item.id: normalize(item.name) for item in session.scalars(select(Label).where(Label.organization_id == organization_id)).all()}
        assigned = event_label_ids(session, [event.id for event in events])

        def text_of(event: Event) -> str:
            parts = [event.title, plain_text(event.description, event.description_format), event.location or "", *(item.get("title", "") for item in event.links or [])]
            return " ".join(normalize(part) for part in parts) + " " + categories.get(event.category_id, "") + " " + " ".join(labels.get(label_id, "") for label_id in assigned.get(event.id, []))

        matches = [event for event in events if not (occurrences.get(event.id) and occurrences[event.id].skipped) and needle in text_of(event)]
        page = matches[offset : offset + PAGE_SIZE]
        return SearchResponse(
            items=[_linked(_response(event, occurrences.get(event.id), assigned.get(event.id, [])), links.get(event.lane_id) if event.yearclock_id != yearclock_id else None) for event in page],
            next_offset=offset + PAGE_SIZE if offset + PAGE_SIZE < len(matches) else None,
            total=len(matches),
            includes_recurring=any(event.id in occurrences for event in matches),
        )


def _linked(response: EventResponse, link: tuple[UUID, UUID] | None) -> EventResponse:
    """Show an Event of a Source Lane on its Linked Lane, as the Event list does."""
    return response.model_copy(update={"lane_id": link[0], "linked": True, "source_yearclock_id": link[1]}) if link else response
