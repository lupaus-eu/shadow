from datetime import UTC, datetime, timedelta
from time import sleep

from app.database import RequestContext, create_database_engine, create_session_factory, transaction_session
from app.email_delivery import EmailMessage, ScalewayEmailSettings, ScalewayTransactionalEmailClient, TransactionalEmailSender
from app.models import OutboxMessage
from app.work_queue import claim_next_outbox_message, complete_queue_record, fail_queue_record, retry_queue_record

MAX_EMAIL_ATTEMPTS = 3


EMAIL_TOPICS = ("organization.invitation", "notification", "summary", "billing.contact_changed")


def deliver_one_email(session_factory, sender: TransactionalEmailSender) -> bool:
    """Send one queued email (an Invitation or a notification); False when none is due."""
    for topic in EMAIL_TOPICS:
        if _deliver_one(session_factory, sender, topic):
            return True
    return False


def deliver_one_invitation_email(session_factory, sender: TransactionalEmailSender) -> bool:
    return _deliver_one(session_factory, sender, "organization.invitation")


def _deliver_one(session_factory, sender: TransactionalEmailSender, topic: str) -> bool:
    with transaction_session(session_factory, RequestContext()) as session:
        message = claim_next_outbox_message(session, topic=topic)
        if message is None:
            return False
        message_id = message.id
        payload = dict(message.payload)
        attempts = message.attempts
        key = message.idempotency_key
    try:
        if payload.get("to") is None or payload.get("subject") is None or payload.get("text") is None:
            raise ValueError("invalid email payload")
        provider_id = sender.send(EmailMessage(str(payload["to"]), str(payload["subject"]), str(payload["text"]), key))
    except Exception as error:
        with transaction_session(session_factory, RequestContext()) as session:
            record = session.get(OutboxMessage, message_id)
            if record is not None:
                if attempts >= MAX_EMAIL_ATTEMPTS:
                    fail_queue_record(record, error=str(error)[:500])
                else:
                    retry_queue_record(record, error=str(error)[:500], available_at=datetime.now(UTC) + timedelta(minutes=2 ** attempts))
        return True
    with transaction_session(session_factory, RequestContext()) as session:
        record = session.get(OutboxMessage, message_id)
        if record is not None:
            record.provider_message_id = provider_id
            complete_queue_record(record)
    return True


def main() -> None:
    import os
    from app.jobs import run_one_background_job, schedule_notification_cleanup_jobs, schedule_organization_purge_jobs, schedule_purge_jobs, schedule_recurrence_jobs
    from app.summary import schedule_summary_jobs
    from app.legal_announcements import schedule_legal_announcements
    from app.legal_documents import LegalLibrary
    from app.support_access_routes import expire_support_access

    legal_library = LegalLibrary.from_environment()
    engine = create_database_engine(os.environ["DATABASE_URL"])
    session_factory = create_session_factory(engine)
    sender = ScalewayTransactionalEmailClient(ScalewayEmailSettings.from_environment())
    schedule_interval = timedelta(seconds=int(os.getenv("WORKER_SCHEDULE_INTERVAL_SECONDS", "3600")))
    next_schedule = datetime.now(UTC)
    next_expiry_sweep = datetime.now(UTC)
    while True:
        now = datetime.now(UTC)
        if now >= next_expiry_sweep:
            expire_support_access(session_factory, now=now)
            next_expiry_sweep = now + timedelta(minutes=1)
        if now >= next_schedule:
            schedule_recurrence_jobs(session_factory, today=now.date())
            schedule_purge_jobs(session_factory, today=now.date())
            schedule_notification_cleanup_jobs(session_factory, today=now.date())
            schedule_summary_jobs(session_factory, now=now)
            schedule_organization_purge_jobs(session_factory, now=now)
            schedule_legal_announcements(session_factory, legal_library, now=now)
            next_schedule = now + schedule_interval
        delivered = deliver_one_email(session_factory, sender)
        ran = run_one_background_job(session_factory)
        if not delivered and not ran:
            sleep(1)


if __name__ == "__main__":
    main()
