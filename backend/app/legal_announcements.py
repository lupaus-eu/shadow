"""Telling Owners about a newly published legal document version, once (ADR-0041).

``schedule_legal_announcements`` runs with the other daily jobs: for each published document version that is not
in ``legal_announcements`` it enqueues one ``legal.announce`` job per active Organization and records the
announcement. The job notifies the Owners (in the app and by mandatory email) unless the Organization has
already accepted that version, as a new Organization does at sign-up.
"""
from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from app.database import RequestContext, transaction_session
from app.legal_documents import LegalLibrary
from app.models import BackgroundJob, LegalAcceptance, LegalAnnouncement, Organization, OrganizationMembership, OrganizationRole, OrganizationStatus
from app.notifications import LEGAL_DOCUMENT_PUBLISHED, NotificationDraft, notify_many
from app.work_queue import BackgroundJobDraft, enqueue_background_job

ANNOUNCE_JOB = "legal.announce"


def schedule_legal_announcements(session_factory: sessionmaker[Session], library: LegalLibrary, *, now: datetime) -> int:
    """Enqueue the announcements of versions not yet announced; returns the number of jobs enqueued."""
    with transaction_session(session_factory, RequestContext()) as session:
        announced = {(row.document_key, row.version) for row in session.scalars(select(LegalAnnouncement)).all()}
    pending = [document for document in library.published("en") if (document.key, document.version) not in announced]
    if not pending:
        return 0
    with transaction_session(session_factory, RequestContext(worker_scope="enumerate")) as session:
        organization_ids = session.scalars(select(Organization.id).where(Organization.status == OrganizationStatus.ACTIVE.value)).all()
    enqueued = 0
    for document in pending:
        payload = {"document_key": document.key, "version": document.version, "effective_from": document.effective_from.isoformat(), "acceptance": document.acceptance}
        for organization_id in organization_ids:
            with transaction_session(session_factory, RequestContext(organization_id=organization_id)) as session:
                enqueue_background_job(session, BackgroundJobDraft(job_type=ANNOUNCE_JOB, payload=payload, idempotency_key=f"{ANNOUNCE_JOB}:{organization_id}:{document.key}:{document.version}"))
            enqueued += 1
        # Recorded after the jobs are queued; a crash in between only repeats idempotent enqueues.
        with transaction_session(session_factory, RequestContext()) as session:
            session.execute(insert(LegalAnnouncement).values(document_key=document.key, version=document.version).on_conflict_do_nothing())
    return enqueued


def announce_document(session: Session, job: BackgroundJob, now: datetime) -> None:
    """Notify the Owners of one Organization about one published version."""
    organization_id: UUID = job.organization_id
    organization = session.get(Organization, organization_id)
    if organization is None or organization.status != OrganizationStatus.ACTIVE.value:
        return
    payload = job.payload
    key, version = str(payload["document_key"]), int(payload["version"])
    already = session.scalar(select(LegalAcceptance.id).where(LegalAcceptance.organization_id == organization_id, LegalAcceptance.document_key == key, LegalAcceptance.version >= version))
    if already is not None:
        return
    owners = session.scalars(select(OrganizationMembership.user_account_id).where(OrganizationMembership.organization_id == organization_id, OrganizationMembership.role == OrganizationRole.OWNER.value)).all()
    params = {"document_key": key, "version": version, "effective_from": payload["effective_from"], "acceptance": payload["acceptance"]}
    notify_many(session, organization_id, [NotificationDraft(owner, LEGAL_DOCUMENT_PUBLISHED, params) for owner in owners])


AnnounceScheduler = Callable[[sessionmaker[Session], LegalLibrary], int]
