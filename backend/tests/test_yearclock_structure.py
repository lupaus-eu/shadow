from fastapi.testclient import TestClient

from app.main import create_app
from test_invitations import NOW, OIDC, Stripe, Verifier, active_org, login


def test_owner_manages_yearclock_and_lane_lifecycle(database_url: str) -> None:
    verifier = Verifier()
    application = create_app(
        database_url=database_url,
        oidc_client=OIDC("structure-owner", "structure-owner@example.com"),
        stripe_billing=Stripe(),
        stripe_webhook_verifier=verifier,
        clock=lambda: NOW,
    )
    with TestClient(application) as client:
        login(client)
        organization_id = active_org(client, verifier)
        base = f"/api/v1/organizations/{organization_id}/yearclocks"
        created = client.post(base, json={"name": "Board cycle"})
        assert created.status_code == 201
        yearclock = created.json()

        renamed = client.patch(
            f"{base}/{yearclock['id']}",
            json={"name": "Board calendar", "expected_version": 1},
        )
        assert renamed.status_code == 200
        yearclock = renamed.json()

        created_lane = client.post(
            f"{base}/{yearclock['id']}/lanes",
            json={"name": "Finance"},
        )
        assert created_lane.status_code == 201
        reordered = client.put(
            f"{base}/{yearclock['id']}/lanes/order",
            json={
                "ordered_ids": [created_lane.json()["id"], yearclock["lanes"][0]["id"]],
                "expected_version": yearclock["version"],
            },
        )
        assert [lane["name"] for lane in reordered.json()] == ["Finance", "General"]

        archived = client.post(
            f"{base}/{yearclock['id']}/archive",
            json={"name": "Board calendar", "expected_version": yearclock["version"] + 1},
        )
        assert archived.status_code == 200
        assert archived.json()["archived_at"] is not None
        assert all(item["id"] != yearclock["id"] for item in client.get(base).json())

        restored = client.post(
            f"{base}/{yearclock['id']}/restore",
            json={"name": "Board calendar", "expected_version": archived.json()["version"]},
        )
    assert restored.status_code == 200
    assert restored.json()["archived_at"] is None


def test_yearclock_order_requires_current_versions(database_url: str) -> None:
    verifier = Verifier()
    application = create_app(database_url=database_url, oidc_client=OIDC("order-owner", "order-owner@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
    with TestClient(application) as client:
        login(client)
        organization_id = active_org(client, verifier)
        base = f"/api/v1/organizations/{organization_id}/yearclocks"
        first = client.get(base).json()[0]
        second = client.post(base, json={"name": "Board cycle"}).json()
        versions = {first["id"]: first["version"], second["id"]: second["version"]}
        reordered = client.put(f"{base}/order", json={"ordered_ids": [second["id"], first["id"]], "expected_versions": versions})
        stale = client.put(f"{base}/order", json={"ordered_ids": [first["id"], second["id"]], "expected_versions": versions})
        duplicate = client.put(f"{base}/order", json={"ordered_ids": [first["id"], first["id"]], "expected_versions": versions})
        listed = [item["name"] for item in client.get(base).json()]
    assert reordered.status_code == 200
    assert [item["id"] for item in reordered.json()] == [second["id"], first["id"]]
    assert stale.status_code == 409
    assert set(stale.json()["detail"]["latest_versions"]) == {first["id"], second["id"]}
    assert duplicate.status_code == 422
    assert listed == ["Board cycle", first["name"]]
