"""Organization deletion: Pending Deletion, the recovery window, restore, and purge (ticket 21)."""
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.database import RequestContext, create_session_factory, transaction_session
from app.jobs import ORGANIZATION_PURGE_JOB, run_one_background_job, schedule_organization_purge_jobs
from app.main import create_app
from test_invitations import NOW, OIDC, Stripe, Verifier, active_org, join, login
from test_platform_operations import _platform_app, platform_login


@pytest.fixture
def stack():
    with ExitStack() as clients:
        yield clients


def _organization(stack: ExitStack, database_url: str, subject: str):
    verifier = Verifier()
    application = create_app(database_url=database_url, oidc_client=OIDC(subject, f"{subject}@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
    owner = stack.enter_context(TestClient(application))
    login(owner)
    organization_id = active_org(owner, verifier, seats=4)
    return application, owner, organization_id, None


def _age_request(application, organization_id: str, days: int) -> None:
    with application.state.database_engine.begin() as connection:
        connection.execute(text("UPDATE organizations SET deletion_requested_at = now() - make_interval(days => :days) WHERE id = :id"), {"days": days, "id": organization_id})


def _count(application, table: str, organization_id: str) -> int:
    with application.state.database_engine.connect() as connection:
        return connection.execute(text(f"SELECT count(*) FROM {table} WHERE organization_id = :id"), {"id": organization_id}).scalar_one()


def test_audit_summaries_can_only_be_emptied_by_the_purge_scope(database_url: str, stack: ExitStack) -> None:
    application, _, organization_id, _ = _organization(stack, database_url, "audit-guard-owner")
    session_factory = create_session_factory(application.state.database_engine)
    with transaction_session(session_factory, RequestContext(organization_id=organization_id)) as session:
        assert session.execute(text("UPDATE audit_events SET change_summary = '{}'::jsonb")).rowcount == 0
    with pytest.raises(DBAPIError):
        with transaction_session(session_factory, RequestContext(organization_id=organization_id, worker_scope="purge")) as session:
            session.execute(text("UPDATE audit_events SET change_summary = '{\"x\": 1}'::jsonb"))
    with pytest.raises(DBAPIError):
        with transaction_session(session_factory, RequestContext(organization_id=organization_id, worker_scope="purge")) as session:
            session.execute(text("UPDATE audit_events SET action = 'forged'"))


def _count_jobs(application, organization_id: str, job_type: str) -> int:
    with application.state.database_engine.connect() as connection:
        return connection.execute(text("SELECT count(*) FROM background_jobs WHERE organization_id = :id AND job_type = :type"), {"id": organization_id, "type": job_type}).scalar_one()


def _count_other_jobs(application, organization_id: str) -> int:
    with application.state.database_engine.connect() as connection:
        return connection.execute(text("SELECT count(*) FROM background_jobs WHERE organization_id = :id AND job_type <> :type"), {"id": organization_id, "type": ORGANIZATION_PURGE_JOB}).scalar_one()
