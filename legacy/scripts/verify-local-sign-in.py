#!/usr/bin/env python3
"""Verify sign-in to Shadow through the local Authentik, end to end (ADR-017).

Run against the local stack (`make dev-up`; the backend, Caddy and Authentik must be up and
the seeded users present):

    python3 scripts/verify-local-sign-in.py

It drives the browser's path with the standard library only: Shadow's login redirect to
Authentik, the password and TOTP steps of the seeded development user, the authorization
code to Shadow's callback, the session, and the sign-out that ends both sessions through
`id_token_hint`. It also checks that a person whose email is not verified, and a person
Shadow does not know, are refused without a session.

Precondition: the seeded dev-consultant has not signed in to Shadow before in this database
(its refusals come from the email rules; a user already linked by subject would sign in
whatever the email says). The script never signs it in successfully.
"""

import importlib.util
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("authentik_local", ROOT / "scripts" / "verify-authentik-local.py")
assert spec is not None and spec.loader is not None
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)

APP = "https://app.localhost"
ADMIN = {"Authorization": f"Bearer {helpers.TOKEN}"}


def start_login(client: urllib.request.OpenerDirector) -> str:
    """Shadow's login endpoint; returns the Authentik authorization URL it redirects to."""
    status, headers, _ = helpers.call(client, f"{APP}/api/v1/auth/login?return_to=/workspace")
    helpers.check(status == 302, "Shadow redirects the login to the identity provider")
    location = headers["Location"]
    helpers.check(location.startswith(f"{helpers.BASE}/application/o/authorize/"), "the redirect goes to Authentik's authorize endpoint")
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(location).query)
    helpers.check(query["code_challenge_method"] == ["S256"] and query["client_id"] == [helpers.CLIENT_ID], "the request uses S256 PKCE and the web client")
    return location


def finish_login(client: urllib.request.OpenerDirector, authorize_url: str, username: str) -> tuple[int, str]:
    """Sign `username` in at Authentik, then follow the code to Shadow's callback."""
    status, headers, _ = helpers.call(client, authorize_url)
    helpers.check(status == 302 and "default-authentication-flow" in headers["Location"], "an unauthenticated visitor is sent to the sign-in flow")
    result = helpers.sign_in(client, username, with_second_factor=True)
    helpers.check(result.get("component") == "xak-flow-redirect", f"{username} completes password and second factor")
    status, headers, _ = helpers.call(client, authorize_url)
    helpers.check(status == 302, "the authorization request now returns a code")
    callback = headers["Location"]
    helpers.check(callback.startswith(f"{APP}/api/v1/auth/callback?code="), "the code goes to Shadow's callback")
    status, headers, _ = helpers.call(client, callback)
    return status, headers.get("Location", "")


def session_status(client: urllib.request.OpenerDirector) -> tuple[int, dict[str, object]]:
    status, _, body = helpers.call(client, f"{APP}/api/v1/auth/session", headers={"Accept": "application/json"})
    return status, json.loads(body) if status == 200 else {}


def patch_user(pk: int, **attributes: object) -> None:
    request = urllib.request.Request(
        f"{helpers.BASE}/api/v3/core/users/{pk}/",
        method="PATCH",
        data=json.dumps(attributes).encode(),
        headers=ADMIN | {"Content-Type": "application/json"},
    )
    helpers.opener().open(request, timeout=20)


def main() -> None:
    # 1. A seeded user signs in and out.
    client = helpers.opener()
    authorize_url = start_login(client)
    status, location = finish_login(client, authorize_url, "dev-admin")
    helpers.check(status == 303 and location == f"{APP}/workspace", "the callback signs the person in and returns to the requested page")
    status, session = session_status(client)
    user = session.get("user", {}) if isinstance(session.get("user"), dict) else {}
    helpers.check(status == 200 and user.get("email") == "admin@example.local" and user.get("role") == "admin", "Shadow's session is the seeded admin account (linked by verified email)")
    helpers.check("id_token" not in json.dumps(session), "the session response carries no token")
    csrf = str(session["csrfToken"])
    status, _, body = helpers.call(client, f"{APP}/api/v1/auth/logout", data={}, headers={"Origin": APP, "X-CSRF-Token": csrf})
    helpers.check(status == 200, "sign-out succeeds")
    logout_url = json.loads(body)["logoutUrl"]
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(logout_url).query)
    helpers.check("id_token_hint" in query and query["post_logout_redirect_uri"] == [f"{APP}/login"], "the sign-out URL carries the ID token hint and the exact return address")
    helpers.check(session_status(client)[0] == 401, "Shadow's session is gone")
    # Authentik's end-session page runs its invalidation flow (the sign-out of the single
    # sign-on session) and then sends the person to the registered return address.
    status, headers, _ = helpers.call(client, logout_url)
    helpers.check(status == 302 and "default-invalidation-flow" in headers["Location"], "Authentik's end-session endpoint starts the invalidation flow")
    ending = helpers.challenge(client, helpers.executor(client, "default-invalidation-flow"))
    helpers.check(ending.get("component") == "xak-flow-redirect" and ending["to"] == f"{APP}/login", "Authentik signs the person out and returns to Shadow's login page")
    status, _, _ = helpers.call(client, f"{helpers.BASE}/api/v3/core/users/me/", headers={"Accept": "application/json"})
    helpers.check(status in (401, 403), "Authentik's session is gone too")

    # 2. An unverified or unknown person is refused, and gets no session.
    consultant = next(u for u in helpers.api("core/users/?username=dev-consultant")["results"])
    pk = consultant["pk"]
    try:
        # The email stays that of a seeded Shadow user, but is no longer the address that was
        # verified: only the verification rule can refuse this sign-in.
        patch_user(pk, attributes={"shadow_verified_email": "someone.else@example.test"})
        refused = helpers.opener()
        status, location = finish_login(refused, start_login(refused), "dev-consultant")
        helpers.check(status == 303 and location.startswith(f"{APP}/") and "workspace" not in location, "an address that is no longer verified is refused")
        helpers.check(session_status(refused)[0] == 401, "and no session is created")

        patch_user(pk, email="stranger@example.test", attributes={"shadow_verified_email": "stranger@example.test"})
        unknown = helpers.opener()
        status, location = finish_login(unknown, start_login(unknown), "dev-consultant")
        helpers.check(status == 303 and "workspace" not in location, "a verified person Shadow does not know is refused")
        helpers.check(session_status(unknown)[0] == 401, "and no session is created")
    finally:
        patch_user(pk, email="consultant@example.local", attributes={"shadow_verified_email": "consultant@example.local"})
    print("Sign-in through Authentik verified.")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as error:
        print(f"FAIL {error}")
        sys.exit(1)
