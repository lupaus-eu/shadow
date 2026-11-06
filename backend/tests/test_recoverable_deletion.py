"""Recoverable deletion and purge of Events and Yearclocks (ticket 16)."""
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.jobs import PURGE_JOB, run_one_background_job, schedule_purge_jobs
from app.main import create_app
from test_invitations import NOW, OIDC, Stripe, Verifier, active_org, join, login


def _setup(database_url: str, subject: str):
    verifier = Verifier()
    application = create_app(database_url=database_url, oidc_client=OIDC(subject, f"{subject}@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
    return application, verifier


def _count(engine, sql: str, **params) -> int:
    with engine.connect() as connection:
        return connection.execute(text(sql), params).scalar_one()


def test_a_deleted_yearclock_and_its_content_are_hidden_and_recoverable(database_url: str) -> None:
    owner_app, verifier = _setup(database_url, "recover-owner")
    with TestClient(owner_app) as owner:
        login(owner)
        organization_id = active_org(owner, verifier)
        member_app, member_id = join(owner_app, owner, organization_id, subject="recover-member", email="recover-member@example.com")
        orgs = f"/api/v1/organizations/{organization_id}"
        clock = owner.post(f"{orgs}/yearclocks", json={"name": "Board"}).json()
        base = f"{orgs}/yearclocks/{clock['id']}"
        category = owner.post(f"{base}/categories", json={"name": "Governance"}).json()
        event = owner.post(f"{base}/events", json={"title": "AGM", "lane_id": clock["lanes"][0]["id"], "category_id": category["id"], "starts_on": "2026-05-20"}).json()
        owner.post(f"{base}/series", json={"title": "Board meeting", "lane_id": clock["lanes"][0]["id"], "starts_on": "2026-01-15", "frequency": "MONTHLY"})
        owner.put(f"{base}/access", json={"user_account_id": member_id, "role": "editor"})
        stale = owner.delete(f"{base}?expected_version=99")
        deleted = owner.delete(f"{base}?expected_version={clock['version']}")
        workspace = [item["name"] for item in owner.get(orgs).json()["yearclocks"]]
        listed = [item["name"] for item in owner.get(f"{orgs}/yearclocks").json()]
        with_deleted = next(item for item in owner.get(f"{orgs}/yearclocks?include_deleted=true").json() if item["id"] == clock["id"])
        hidden = [owner.get(f"{base}/events").status_code, owner.get(f"{base}/categories").status_code, owner.post(f"{base}/lanes", json={"name": "X"}).status_code, owner.patch(base, json={"name": "Renamed", "expected_version": with_deleted["version"]}).status_code]
    with TestClient(member_app) as member:
        login(member)
        member_hidden = member.get(f"{base}/events").status_code
    with TestClient(owner_app) as owner:
        login(owner)
        recovered = owner.post(f"{base}/recover?expected_version={with_deleted['version']}")
        events = owner.get(f"{base}/events?window_start=2026-01-01").json()
    with TestClient(member_app) as member:
        login(member)
        member_edit = member.post(f"{base}/events", json={"title": "After recovery", "lane_id": clock["lanes"][0]["id"], "starts_on": "2026-06-01"}).status_code
    assert stale.status_code == 409
    assert deleted.status_code == 204
    assert "Board" not in workspace and "Board" not in listed
    purge_after = datetime.fromisoformat(with_deleted["purge_after"]) - datetime.fromisoformat(with_deleted["deleted_at"])
    assert purge_after == timedelta(days=30)
    assert hidden == [404, 404, 404, 404]
    assert member_hidden == 404
    assert recovered.status_code == 200 and recovered.json()["deleted_at"] is None
    agm = next(item for item in events if item["id"] == event["id"])
    assert agm["category_id"] == category["id"]
    assert len([item for item in events if item["series_id"]]) == 12
    assert member_edit == 201
    with owner_app.state.database_engine.connect() as connection:
        actions = connection.execute(text("SELECT action FROM audit_events WHERE target_id = :id AND action LIKE 'yearclock.%' ORDER BY occurred_at"), {"id": clock["id"]}).scalars().all()
    assert actions == ["yearclock.created", "yearclock.deleted", "yearclock.recovered"]


def test_recurring_occurrences_use_series_operations_instead_of_delete(database_url: str) -> None:
    application, verifier = _setup(database_url, "recover-recurring")
    with TestClient(application) as client:
        login(client)
        organization_id = active_org(client, verifier)
        clock = client.get(f"/api/v1/organizations/{organization_id}").json()["yearclocks"][0]
        base = f"/api/v1/organizations/{organization_id}/yearclocks/{clock['id']}"
        client.post(f"{base}/series", json={"title": "Weekly", "lane_id": clock["lanes"][0]["id"], "starts_on": "2026-01-05", "frequency": "WEEKLY"})
        occurrence = client.get(f"{base}/events?window_start=2026-01-01").json()[0]
        response = client.delete(f"{base}/events/{occurrence['id']}?expected_version={occurrence['version']}")
    assert response.status_code == 409
    assert response.json()["detail"]["reason"] == "recurring_occurrence"


def test_the_purge_job_removes_only_expired_content_idempotently(database_url: str) -> None:
    application, verifier = _setup(database_url, "recover-purge")
    engine, factory = application.state.database_engine, application.state.session_factory
    with TestClient(application) as client:
        login(client)
        organization_id = active_org(client, verifier)
        orgs = f"/api/v1/organizations/{organization_id}"
        general = client.get(orgs).json()["yearclocks"][0]
        base = f"{orgs}/yearclocks/{general['id']}"
        old_event = client.post(f"{base}/events", json={"title": "Old", "lane_id": general["lanes"][0]["id"], "starts_on": "2026-02-01"}).json()
        recent_event = client.post(f"{base}/events", json={"title": "Recent", "lane_id": general["lanes"][0]["id"], "starts_on": "2026-02-02"}).json()
        client.delete(f"{base}/events/{old_event['id']}?expected_version=1")
        client.delete(f"{base}/events/{recent_event['id']}?expected_version=1")
        old_clock = client.post(f"{orgs}/yearclocks", json={"name": "Old plan"}).json()
        old_base = f"{orgs}/yearclocks/{old_clock['id']}"
        client.post(f"{old_base}/categories", json={"name": "Old"})
        client.post(f"{old_base}/events", json={"title": "Secret", "lane_id": old_clock["lanes"][0]["id"], "starts_on": "2026-03-03"})
        client.post(f"{old_base}/series", json={"title": "Old series", "lane_id": old_clock["lanes"][0]["id"], "starts_on": "2026-01-01", "frequency": "MONTHLY"})
        client.delete(f"{old_base}?expected_version={old_clock['version']}")
    now = datetime.now(UTC)
    with engine.begin() as connection:
        connection.execute(text("UPDATE events SET deleted_at = :at WHERE id = :id"), {"at": now - timedelta(days=31), "id": old_event["id"]})
        connection.execute(text("UPDATE events SET deleted_at = :at WHERE id = :id"), {"at": now - timedelta(days=10), "id": recent_event["id"]})
        connection.execute(text("UPDATE yearclocks SET deleted_at = :at WHERE id = :id"), {"at": now - timedelta(days=31), "id": old_clock["id"]})

    schedule_purge_jobs(factory, today=now.date())
    while run_one_background_job(factory, organization_id=UUID(organization_id)):
        pass
    schedule_purge_jobs(factory, today=now.date())
    assert _count(engine, "SELECT count(*) FROM background_jobs WHERE organization_id = :id AND job_type = :type", id=organization_id, type=PURGE_JOB) == 1
    assert _count(engine, "SELECT count(*) FROM events WHERE id = :id", id=old_event["id"]) == 0
    assert _count(engine, "SELECT count(*) FROM events WHERE id = :id", id=recent_event["id"]) == 1
    for table in ("yearclocks WHERE id", "lanes WHERE yearclock_id", "events WHERE yearclock_id", "event_series WHERE yearclock_id", "categories WHERE yearclock_id"):
        assert _count(engine, f"SELECT count(*) FROM {table} = :id", id=old_clock["id"]) == 0, table
    assert _count(engine, "SELECT count(*) FROM yearclocks WHERE id = :id", id=general["id"]) == 1
    with engine.connect() as connection:
        purged = connection.execute(text("SELECT action, change_summary FROM audit_events WHERE organization_id = :id AND action LIKE '%.purged'"), {"id": organization_id}).all()
    assert sorted(action for action, _ in purged) == ["event.purged", "yearclock.purged"]
    assert all(summary == {} for _, summary in purged)

    with engine.begin() as connection:
        connection.execute(text("UPDATE background_jobs SET status = 'pending', available_at = now() WHERE organization_id = :id AND job_type = :type"), {"id": organization_id, "type": PURGE_JOB})
    assert run_one_background_job(factory, organization_id=UUID(organization_id))
    assert _count(engine, "SELECT count(*) FROM background_jobs WHERE organization_id = :id AND status = 'completed' AND job_type = :type", id=organization_id, type=PURGE_JOB) == 1


def test_read_only_state_blocks_deletion_and_restoration_but_not_viewing(database_url: str) -> None:
    application, verifier = _setup(database_url, "recover-readonly")
    with TestClient(application) as client:
        login(client)
        organization_id = active_org(client, verifier)
        orgs = f"/api/v1/organizations/{organization_id}"
        clock = client.get(orgs).json()["yearclocks"][0]
        base = f"{orgs}/yearclocks/{clock['id']}"
        event = client.post(f"{base}/events", json={"title": "Plan", "lane_id": clock["lanes"][0]["id"], "starts_on": "2026-04-01"}).json()
        client.delete(f"{base}/events/{event['id']}?expected_version=1")
        with application.state.database_engine.begin() as connection:
            connection.execute(text("UPDATE organizations SET subscription_access_state = 'read_only' WHERE id = :id"), {"id": organization_id})
        restore = client.post(f"{base}/events/{event['id']}/restore?expected_version=2")
        delete_clock = client.delete(f"{base}?expected_version={clock['version']}")
        deleted_list = client.get(f"{base}/deleted-events")
        events = client.get(f"{base}/events")
    assert restore.status_code == 403
    assert delete_clock.status_code == 403
    assert deleted_list.status_code == 200 and [item["title"] for item in deleted_list.json()] == ["Plan"]
    assert events.status_code == 200
