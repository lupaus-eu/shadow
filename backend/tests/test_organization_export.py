"""The Organization Export (Yearclock V2, P7 ticket 04)."""
import json
import time
from contextlib import ExitStack
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.label_routes import LABEL_COLORS
from app.main import create_app
from test_invitations import NOW, OIDC, Stripe, Verifier, active_org, join, login


@pytest.fixture
def stack():
    with ExitStack() as clients:
        yield clients


class World:
    def __init__(self, stack, database_url, subject):
        verifier = Verifier()
        self.application = create_app(database_url=database_url, oidc_client=OIDC(subject, f"{subject}@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
        self.owner = stack.enter_context(TestClient(self.application))
        login(self.owner)
        self.organization_id = active_org(self.owner, verifier, seats=6)
        self.org = f"/api/v1/organizations/{self.organization_id}"
        self.clock = self.owner.get(self.org).json()["yearclocks"][0]
        self.base = f"{self.org}/yearclocks/{self.clock['id']}"
        self.lane = self.clock["lanes"][0]["id"]

    def export(self, client=None):
        return (client or self.owner).get(f"{self.org}/export")

    def audit(self):
        return [item for item in self.owner.get(f"{self.org}/audit-events", params={"prefix": "organization"}).json()["items"] if item["action"] == "organization.export"]


def test_an_owner_downloads_the_content_of_the_organization(database_url, stack) -> None:
    world = World(stack, database_url, "orgexport-content")
    label = world.owner.post(f"{world.org}/labels", json={"name": "Draft", "color": LABEL_COLORS[0]}).json()
    shared = world.owner.post(f"{world.org}/categories", json={"name": "Board", "color": "#1f5f99"}).json()
    own = world.owner.post(f"{world.base}/categories", json={"name": "Local", "color": "#336699"}).json()
    plain = world.owner.post(f"{world.base}/events", json={"title": "Board meeting", "lane_id": world.lane, "starts_on": "2026-10-01", "ends_on": "2026-10-02", "category_id": shared["id"], "label_ids": [label["id"]], "description": "Agenda", "links": [{"title": "Agenda", "url": "https://example.com/a"}]}).json()
    gone = world.owner.post(f"{world.base}/events", json={"title": "Deleted", "lane_id": world.lane, "starts_on": "2026-10-03"}).json()
    assert world.owner.delete(f"{world.base}/events/{gone['id']}", params={"expected_version": gone["version"]}).status_code == 204
    world.owner.post(f"{world.base}/series", json={"title": "Standup", "lane_id": world.lane, "starts_on": "2026-10-05", "frequency": "WEEKLY", "label_ids": [label["id"]]})
    world.owner.get(f"{world.base}/events", params={"window_start": "2026-10-01", "months": 1})
    deleted_clock = world.owner.post(f"{world.org}/yearclocks", json={"name": "Deleted clock"}).json()
    assert world.owner.delete(f"{world.org}/yearclocks/{deleted_clock['id']}", params={"expected_version": deleted_clock["version"]}).status_code in {200, 204}
    group = world.owner.post(f"{world.org}/groups", json={"name": "Board group"}).json()
    _, member_id = join(world.application, world.owner, world.organization_id, subject="orgexport-member", email="orgexport-member@example.com")
    memberships = world.owner.get(f"{world.org}/memberships").json()
    member = next(item for item in memberships if item["user_account_id"] == member_id)
    assert world.owner.put(f"{world.base}/access", json={"user_account_id": member_id, "role": "viewer"}).status_code == 200
    assert world.owner.put(f"{world.base}/group-access", json={"group_id": group["id"], "role": "editor"}).status_code == 200
    assert world.owner.post(f"{world.org}/groups/{group['id']}/members/{member['id']}").status_code in {200, 201, 204} or world.owner.put(f"{world.org}/groups/{group['id']}/members/{member['id']}").status_code in {200, 201, 204}

    response = world.export()
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/json") and response.headers["cache-control"] == "no-store"
    assert response.headers["content-disposition"].startswith('attachment; filename="') and response.headers["content-disposition"].endswith('.json"')
    document = json.loads(response.content)
    assert document["schema"] == "yearclock-export/2" and document["exported_at"]
    assert set(document) == {"schema", "exported_at", "organization", "members", "groups", "labels", "organization_categories", "yearclocks"}
    assert document["organization"]["id"] == world.organization_id and set(document["organization"]) == {"id", "name", "time_zone", "default_locale", "status"}
    assert {item["role"] for item in document["members"]} == {"owner", "member"} and {item["email"] for item in document["members"]} == {"orgexport-content@example.com", "orgexport-member@example.com"}
    assert [(item["name"], item["member_ids"]) for item in document["groups"]] == [("Board group", [member["id"]])]
    assert [item["name"] for item in document["labels"]] == ["Draft"] and [item["name"] for item in document["organization_categories"]] == ["Board"]
    assert [item["id"] for item in document["yearclocks"]] == [world.clock["id"]]
    clock = document["yearclocks"][0]
    assert [item["name"] for item in clock["categories"]] == ["Local"] and clock["categories"][0]["id"] == own["id"]
    assert [item["name"] for item in clock["lanes"]] == ["General"] and [item["title"] for item in clock["series"]] == ["Standup"] and clock["series"][0]["label_ids"] == [label["id"]]
    events = {item["title"]: item for item in clock["events"]}
    assert "Deleted" not in events and events["Board meeting"]["label_ids"] == [label["id"]] and events["Board meeting"]["ends_on"] == "2026-10-02" and events["Board meeting"]["id"] == plain["id"]
    occurrences = [item for item in clock["events"] if item["title"] == "Standup"]
    assert len(occurrences) >= 4 and all(item["series_id"] == clock["series"][0]["id"] and item["skipped"] is False for item in occurrences)
    assert clock["access"] == {"members": [{"membership_id": member["id"], "role": "viewer"}], "groups": [{"group_id": group["id"], "role": "editor"}]}


def test_history_audit_billing_and_outbox_are_left_out(database_url, stack) -> None:
    world = World(stack, database_url, "orgexport-exclusions")
    event = world.owner.post(f"{world.base}/events", json={"title": "Edited", "lane_id": world.lane, "starts_on": "2026-10-01"}).json()
    world.owner.patch(f"{world.base}/events/{event['id']}", json={"title": "Edited again", "lane_id": world.lane, "starts_on": "2026-10-01", "expected_version": event["version"]})
    text_ = world.export().text.lower()
    for forbidden in ("revision", "history", "audit", "stripe", "billing", "purchased_seats", "outbox", "subscription", "orgexport-exclusions@example.com\"," + "billing"):
        assert forbidden not in text_, forbidden
    assert "billing_email" not in text_


def test_only_the_owner_may_download_it(database_url, stack) -> None:
    world = World(stack, database_url, "orgexport-roles")
    clients = {}
    for name, role in (("admin", "admin"), ("editor", "member"), ("viewer", "member"), ("member", "member")):
        application, user_id = join(world.application, world.owner, world.organization_id, subject=f"orgexport-{name}", email=f"orgexport-{name}@example.com", role=role)
        clients[name] = stack.enter_context(TestClient(application))
        login(clients[name])
        if name in {"editor", "viewer"}:
            assert world.owner.put(f"{world.base}/access", json={"user_account_id": user_id, "role": name}).status_code == 200
    assert {name: world.export(client).status_code for name, client in clients.items()} == {"admin": 403, "editor": 403, "viewer": 403, "member": 403}
    stranger = stack.enter_context(TestClient(create_app(database_url=database_url, oidc_client=OIDC("orgexport-stranger", "orgexport-stranger@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=Verifier(), clock=lambda: NOW)))
    login(stranger)
    assert world.export(stranger).status_code == 404
    assert world.export().status_code == 200


def test_each_download_is_audited_with_counts_only_and_limited(database_url, stack, monkeypatch) -> None:
    monkeypatch.setenv("LIMIT_ORGANIZATION_EXPORTS_PER_HOUR", "2")
    world = World(stack, database_url, "orgexport-audit")
    world.owner.post(f"{world.base}/events", json={"title": "Secret title", "lane_id": world.lane, "starts_on": "2026-10-01"})
    assert world.export().status_code == 200 and world.export().status_code == 200
    refused = world.export()
    assert refused.status_code == 429 and refused.json()["detail"]["reason"] == "rate_limited" and refused.headers["retry-after"]
    entries = world.audit()
    assert len(entries) == 2
    assert entries[0]["change_summary"] == {"schema": "yearclock-export/2", "members": 1, "groups": 0, "labels": 0, "yearclocks": 1, "events": 1, "series": 0}
    assert "Secret title" not in str(entries)


def test_a_pending_deletion_organization_can_still_be_exported(database_url, stack) -> None:
    world = World(stack, database_url, "orgexport-pending")
    assert world.owner.post(f"{world.org}/deletion", json={"confirm": True}).status_code == 200
    assert world.export().status_code == 200


def test_the_largest_allowed_organization_streams_in_reasonable_time(database_url, stack) -> None:
    world = World(stack, database_url, "orgexport-large")
    organization_id = world.organization_id
    lane_ids, clock_ids = [], []
    with world.application.state.database_engine.begin() as connection:
        for index in range(49):
            clock, lane = uuid4(), uuid4()
            clock_ids.append(clock)
            connection.execute(text("INSERT INTO yearclocks (id, organization_id, name, display_order, version) VALUES (:id, :org, :name, :order, 1)"), {"id": clock, "org": organization_id, "name": f"Clock {index}", "order": index + 1})
            connection.execute(text("INSERT INTO lanes (id, organization_id, yearclock_id, name, display_order, version) VALUES (:id, :org, :clock, 'Lane', 0, 1)"), {"id": lane, "org": organization_id, "clock": clock})
            lane_ids.append(lane)
        connection.execute(text("INSERT INTO events (id, organization_id, yearclock_id, lane_id, title, description, starts_on, version) SELECT gen_random_uuid(), :org, y.id, l.id, 'Event ' || g, repeat('x', 200), DATE '2026-01-01' + (g % 365), 1 FROM yearclocks y JOIN lanes l ON l.yearclock_id = y.id CROSS JOIN generate_series(1, 3000) g WHERE y.organization_id = :org AND y.id <> :first"), {"org": organization_id, "first": world.clock["id"]})
    started = time.perf_counter()
    response = world.export()
    elapsed = time.perf_counter() - started
    document = json.loads(response.content)
    assert response.status_code == 200 and len(document["yearclocks"]) == 50
    assert sum(len(item["events"]) for item in document["yearclocks"]) == 49 * 3000
    print(f"Organization Export, 50 Yearclocks x 3000 Events: {elapsed:.1f} s, {len(response.content) / 1_000_000:.1f} MB")
    assert elapsed < 60, f"the maximum Organization took {elapsed:.1f}s"
