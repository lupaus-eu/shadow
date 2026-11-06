"""Security review checks that are not covered elsewhere (ticket 23)."""
from contextlib import ExitStack
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from test_invitations import NOW, OIDC, Stripe, Verifier, active_org, login


@pytest.fixture
def owner(database_url):
    with ExitStack() as stack:
        verifier = Verifier()
        application = create_app(database_url=database_url, oidc_client=OIDC("security-owner", "security-owner@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
        client = stack.enter_context(TestClient(application))
        login(client)
        organization_id = active_org(client, verifier)
        clock = client.get(f"/api/v1/organizations/{organization_id}").json()["yearclocks"][0]
        yield client, f"/api/v1/organizations/{organization_id}", clock


def test_session_cookie_is_http_only_and_same_site(database_url) -> None:
    application = create_app(database_url=database_url, oidc_client=OIDC("cookie-owner", "cookie-owner@example.com"), clock=lambda: NOW)
    with TestClient(application) as client:
        start = client.get("/api/v1/auth/login", follow_redirects=False)
        state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
        callback = client.get("/api/v1/auth/callback", params={"code": "test", "state": state}, follow_redirects=False)
        replay = client.get("/api/v1/auth/callback", params={"code": "test", "state": state}, follow_redirects=False)
    cookies = [value.lower() for key, value in callback.headers.multi_items() if key.lower() == "set-cookie"]
    session_cookie = next(cookie for cookie in cookies if "path=/api" not in cookie)
    assert "httponly" in session_cookie and "samesite=lax" in session_cookie
    assert replay.status_code >= 400


def test_cross_origin_writes_are_refused(owner) -> None:
    client, base, clock = owner
    body = {"title": "CSRF", "lane_id": clock["lanes"][0]["id"], "starts_on": "2026-10-01"}
    forged = client.post(f"{base}/yearclocks/{clock['id']}/events", json=body, headers={"Origin": "https://evil.example"})
    null_origin = client.post(f"{base}/yearclocks/{clock['id']}/events", json=body, headers={"Origin": "null"})
    trusted = client.post(f"{base}/yearclocks/{clock['id']}/events", json=body, headers={"Origin": "http://localhost:8173"})
    read = client.get(f"{base}/yearclocks/{clock['id']}/events", headers={"Origin": "https://evil.example"})
    assert forged.status_code == 403 and null_origin.status_code == 403
    assert trusted.status_code == 201 and read.status_code == 200
    assert "access-control-allow-origin" not in read.headers


@pytest.mark.parametrize("url", ["javascript:alert(1)", "data:text/html,x", "file:///etc/passwd", "ftp://example.com"])
def test_event_links_accept_only_http_and_https(owner, url) -> None:
    client, base, clock = owner
    response = client.post(f"{base}/yearclocks/{clock['id']}/events", json={"title": "Link", "lane_id": clock["lanes"][0]["id"], "starts_on": "2026-10-01", "links": [{"title": "Link", "url": url}]})
    assert response.status_code == 422


def test_hostile_text_is_stored_verbatim_not_executed(owner) -> None:
    client, base, clock = owner
    title = "'); DROP TABLE events; -- <script>alert(1)</script>"
    created = client.post(f"{base}/yearclocks/{clock['id']}/events", json={"title": title, "lane_id": clock["lanes"][0]["id"], "starts_on": "2026-10-01"})
    listed = client.get(f"{base}/yearclocks/{clock['id']}/events", params={"window_start": "2026-09-01"})
    assert created.status_code == 201 and title in [item["title"] for item in listed.json()]


def test_unsigned_stripe_webhooks_are_rejected(database_url, monkeypatch) -> None:
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setenv("STRIPE_MONTHLY_SEAT_PRICE_ID", "price_x")
    with TestClient(create_app(database_url=database_url), raise_server_exceptions=False) as client:
        response = client.post("/api/v1/billing/stripe/webhook", content=b'{"type": "checkout.session.completed"}', headers={"Stripe-Signature": "t=1,v1=forged", "Origin": "https://evil.example"})
    assert response.status_code == 400, response.text
