"""The Owner's view of the legal documents and the acceptance of a new version (ADR-0041)."""
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.auth import AuthenticatedUser
from app.auth_routes import AuthenticatedUserDependency
from app.legal_acceptance import record_acceptance
from app.legal_documents import KEYS, LegalLibrary
from app.models import LegalAcceptance, OrganizationMembership, UserAccount
from app.subscription_routes import owner_session


class OrganizationLegalDocument(BaseModel):
    key: str
    title: str
    acceptance: Literal["required", "notice", "none"]
    current_version: int
    effective_from: str
    accepted_version: int | None
    accepted_at: datetime | None
    accepted_by_name: str | None
    accepted_by_former_member: bool
    state: Literal["accepted", "acceptance_due", "not_required"]


class OrganizationLegalResponse(BaseModel):
    documents: list[OrganizationLegalDocument]


class AcceptanceRequest(BaseModel):
    document_key: str = Field(min_length=1, max_length=40)
    version: int = Field(ge=1)
    locale: Literal["fi", "en"] = "en"


def _overview(session: Session, library: LegalLibrary, organization_id: UUID, locale: str) -> list[OrganizationLegalDocument]:
    latest: dict[str, LegalAcceptance] = {}
    for row in session.scalars(select(LegalAcceptance).where(LegalAcceptance.organization_id == organization_id).order_by(LegalAcceptance.version)).all():
        latest[row.document_key] = row
    members = {m.user_account_id for m in session.scalars(select(OrganizationMembership).where(OrganizationMembership.organization_id == organization_id)).all()}
    people = {a.id: a.display_name for a in session.scalars(select(UserAccount).where(UserAccount.id.in_({row.user_account_id for row in latest.values() if row.user_account_id}))).all()} if latest else {}
    result = []
    for document in library.published(locale):
        row = latest.get(document.key)
        if document.acceptance != "required":
            state = "not_required"
        else:
            state = "accepted" if row is not None and row.version >= document.version else "acceptance_due"
        by_member = row is not None and row.user_account_id in members
        result.append(
            OrganizationLegalDocument(
                key=document.key,
                title=document.title,
                acceptance=document.acceptance,
                current_version=document.version,
                effective_from=document.effective_from.isoformat(),
                accepted_version=row.version if row else None,
                accepted_at=row.accepted_at if row else None,
                accepted_by_name=people.get(row.user_account_id) if row and by_member else None,
                accepted_by_former_member=row is not None and not by_member,
                state=state,
            )
        )
    return result


def create_organization_legal_router(
    *,
    session_factory: sessionmaker[Session],
    authenticated_user_dependency: AuthenticatedUserDependency,
    library: LegalLibrary,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/organizations/{organization_id}/legal", tags=["organization legal documents"])

    @router.get("", response_model=OrganizationLegalResponse)
    def overview(organization_id: UUID, locale: Literal["fi", "en"] = "en", user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> OrganizationLegalResponse:
        with owner_session(session_factory, organization_id, user) as (session, _):
            return OrganizationLegalResponse(documents=_overview(session, library, organization_id, locale))

    @router.post("/acceptances", response_model=OrganizationLegalDocument)
    def accept(organization_id: UUID, body: AcceptanceRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> OrganizationLegalDocument:
        with owner_session(session_factory, organization_id, user) as (session, _):
            document = next((item for item in library.required() if item.key == body.document_key), None) if body.document_key in KEYS else None
            if document is None:
                raise HTTPException(status_code=404, detail="document not found")
            if body.version != document.version:
                raise HTTPException(status_code=409, detail={"reason": "legal_version_not_current", "current_version": document.version})
            existing = session.scalar(select(LegalAcceptance).where(LegalAcceptance.organization_id == organization_id, LegalAcceptance.document_key == document.key, LegalAcceptance.version == document.version))
            if existing is None:
                record_acceptance(
                    session,
                    organization_id=organization_id,
                    user=user.account,
                    document=document,
                    locale=body.locale,
                    request_id=(request.headers.get("X-Request-ID") or str(uuid4()))[:120],
                )
            overview_rows = _overview(session, library, organization_id, body.locale)
        return next(row for row in overview_rows if row.key == document.key)

    return router
