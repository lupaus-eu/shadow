"""Recording acceptances of required legal documents (ADR-0041)."""
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.audit import AuditEventDraft, record_audit_event
from app.legal_documents import LegalDocument, LegalLibrary
from app.models import LegalAcceptance, UserAccount


def require_acceptances(library: LegalLibrary, accepted: list) -> list[LegalDocument]:
    """The published required documents (English entries) that ``accepted`` covers; 422 listing what is missing."""
    chosen = {(item.document_key, item.version) for item in accepted}
    required = library.required()
    missing = [document for document in required if (document.key, document.version) not in chosen]
    if missing:
        raise HTTPException(
            status_code=422,
            detail={
                "reason": "legal_acceptance_required",
                "required": [{"document_key": document.key, "version": document.version} for document in missing],
            },
        )
    return required


def record_acceptance(
    session: Session,
    *,
    organization_id: UUID,
    user: UserAccount,
    document: LegalDocument,
    locale: str,
    request_id: str,
    audit: bool = True,
) -> LegalAcceptance:
    """Write one acceptance row and, for an Owner's later acceptance, its audit entry."""
    acceptance = LegalAcceptance(
        id=uuid4(),
        organization_id=organization_id,
        user_account_id=user.id,
        accepted_by_email=user.email,
        document_key=document.key,
        version=document.version,
        locale=locale if locale in {"fi", "en"} else "en",
        request_id=request_id,
    )
    session.add(acceptance)
    session.flush()
    if audit:
        record_audit_event(
            session,
            AuditEventDraft(
                action="organization.legal_accepted",
                target_type="organization",
                target_id=organization_id,
                request_id=request_id,
                change_summary={"document_key": document.key, "version": document.version},
            ),
        )
    return acceptance
