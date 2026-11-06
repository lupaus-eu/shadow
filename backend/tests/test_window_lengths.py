"""Planning Window lengths in the Event list (Yearclock V2, P1 ticket 01)."""
from fastapi.testclient import TestClient

from app.main import create_app
from test_invitations import NOW, OIDC, Stripe, Verifier, active_org, login


def test_the_event_list_follows_the_window_length(database_url) -> None:
    verifier = Verifier()
    application = create_app(database_url=database_url, oidc_client=OIDC("window-owner", "window-owner@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
    with TestClient(application) as client:
        login(client)
        organization_id = active_org(client, verifier)
        clock = client.get(f"/api/v1/organizations/{organization_id}").json()["yearclocks"][0]
        events = f"/api/v1/organizations/{organization_id}/yearclocks/{clock['id']}/events"
        for title, day in (("September", "2026-09-15"), ("December", "2026-12-15"), ("Next autumn", "2027-10-15")):
            client.post(events, json={"title": title, "lane_id": clock["lanes"][0]["id"], "starts_on": day})
        titles = lambda months: [item["title"] for item in client.get(events, params={"window_start": "2026-09-01", "months": months}).json()]
        assert titles(1) == ["September"]
        assert titles(3) == ["September"]
        assert titles(6) == ["September", "December"]
        assert titles(24) == ["September", "December", "Next autumn"]
        assert titles(12) == titles(6)
        assert client.get(events, params={"window_start": "2026-09-01", "months": 5}).status_code == 422
