#!/usr/bin/env python3
"""Verify the local Authentik setup end to end (ADR-017, ADR-0023).

Run against the local stack (`make dev-up`):

    python3 scripts/verify-authentik-local.py               # sign-in, MFA, tokens
    python3 scripts/verify-authentik-local.py --enrollment   # needs a stack with AUTHENTIK_ENROLLMENT_OPEN=false

It uses only the standard library. It checks, through https://id.app.localhost with
the local CA (.local/app-tls/ca.crt):

* the web provider's discovery document names the public issuer and end-session URL;
* the declared providers and applications exist with the declared settings;
* a seeded development user must pass a second factor: a sign-in with the password
  alone does not finish; with the TOTP code it does;
* the authorization-code flow with PKCE for the web client returns a code, and the
  token endpoint answers with an ID token whose email is verified (`email_verified`).

Development credentials only; the values come from the environment with the same
defaults as `.env.example`.
"""

import ast
import base64
import hashlib
import hmac
import http.cookiejar
import json
import os
import secrets
import ssl
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
BASE = os.getenv("AUTHENTIK_BASE_URL", "https://id.app.localhost").rstrip("/")
TOKEN = os.getenv("AUTHENTIK_BOOTSTRAP_TOKEN", "local-bootstrap-token-change-me")
PASSWORD = os.getenv("AUTHENTIK_DEV_USER_PASSWORD", "shadow_dev_password")
CLIENT_ID = os.getenv("LOCAL_OIDC_CLIENT_ID", "shadow-local")
CLIENT_SECRET = os.getenv("LOCAL_OIDC_CLIENT_SECRET", "replace-with-a-random-oidc-secret")
REDIRECT_URI = os.getenv("LOCAL_OIDC_REDIRECT_URI", "https://app.localhost/api/v1/auth/callback")
# RFC 6238 test secret used by authentik/dev/provision-dev-totp.py.
TOTP_SECRET = b"12345678901234567890"
CA = ROOT / ".local" / "app-tls" / "ca.crt"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def opener() -> urllib.request.OpenerDirector:
    context = ssl.create_default_context(cafile=str(CA) if CA.exists() else None)
    # The local development CA's leaf has no Authority Key Identifier, which Python 3.13+
    # rejects in strict mode; the chain and the hostname are still verified.
    context.verify_flags &= ~ssl.VERIFY_X509_STRICT
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar),
        urllib.request.HTTPSHandler(context=context),
        NoRedirect(),
    )


def call(
    client: urllib.request.OpenerDirector,
    url: str,
    *,
    data: dict[str, Any] | None = None,
    form: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    body = None
    all_headers = dict(headers or {})
    if data is not None:
        body = json.dumps(data).encode()
        all_headers["Content-Type"] = "application/json"
    if form is not None:
        body = urllib.parse.urlencode(form).encode()
        all_headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = urllib.request.Request(url, data=body, headers=all_headers)
    try:
        with client.open(request, timeout=20) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read()


def api(path: str) -> Any:
    status, _, body = call(opener(), f"{BASE}/api/v3/{path}", headers={"Authorization": f"Bearer {TOKEN}"})
    if status != 200:
        raise AssertionError(f"GET {path} answered HTTP {status}")
    return json.loads(body)


def totp(now: float | None = None) -> str:
    counter = int((now or time.time()) // 30)
    digest = hmac.new(TOTP_SECRET, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{value % 1_000_000:06d}"


_used_steps: set[int] = set()


def totp_code() -> str:
    """A code for a 30-second step not used before: Authentik rejects a replayed code."""
    step = int(time.time() // 30)
    while step in _used_steps or step <= _last_step():
        time.sleep(30 - (time.time() % 30) + 0.5)
        step = int(time.time() // 30)
    _used_steps.add(step)
    _remember_step(step)
    return totp()


STATE = ROOT / ".local" / "authentik-verify-last-step"


def _last_step() -> int:
    try:
        return int(STATE.read_text())
    except (OSError, ValueError):
        return 0


def _remember_step(step: int) -> None:
    try:
        STATE.write_text(str(step))
    except OSError:
        pass


def check(condition: bool, message: str) -> None:
    print(("ok   " if condition else "FAIL ") + message)
    if not condition:
        sys.exit(1)


def executor(client: urllib.request.OpenerDirector, flow: str, query: str = "") -> str:
    suffix = f"?query={urllib.parse.quote(query)}" if query else ""
    return f"{BASE}/api/v3/flows/executor/{flow}/{suffix}"


def challenge(client: urllib.request.OpenerDirector, url: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    status, headers, body = call(client, url, data=data, headers={"Accept": "application/json"})
    for _ in range(3):
        if status not in (301, 302, 303):
            break
        # A submitted stage (or an invitation token) answers with a redirect to the same
        # executor; the next challenge is its GET.
        target = urllib.parse.urljoin(url, headers["Location"])
        status, headers, body = call(client, target, headers={"Accept": "application/json"})
    if status != 200:
        raise AssertionError(f"flow executor answered HTTP {status}: {body[:200]!r}")
    return json.loads(body)


def sign_in(client: urllib.request.OpenerDirector, username: str, *, with_second_factor: bool) -> dict[str, Any]:
    """Drive the default authentication flow; return the last challenge."""
    url = executor(client, "default-authentication-flow")
    current = challenge(client, url)
    for _ in range(12):
        component = current.get("component")
        if component == "ak-stage-identification":
            current = challenge(client, url, {"component": component, "uid_field": username})
        elif component == "ak-stage-password":
            current = challenge(client, url, {"component": component, "password": PASSWORD})
        elif component == "ak-stage-authenticator-validate":
            if not with_second_factor:
                return current
            devices = current["device_challenges"]
            totp_device = next((d for d in devices if d["device_class"] == "totp"), None)
            check(totp_device is not None, f"{username} is offered a TOTP device")
            current = challenge(client, url, {"component": component, "code": totp_code()})
        else:
            return current
    return current


MAILPIT = os.getenv("MAILPIT_URL", "http://localhost:8025").rstrip("/")


def base32_secret(config_url: str) -> bytes:
    secret = urllib.parse.parse_qs(urllib.parse.urlsplit(config_url).query)["secret"][0]
    return base64.b32decode(secret + "=" * (-len(secret) % 8))


def totp_for(secret: bytes, step: int) -> str:
    digest = hmac.new(secret, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{value % 1_000_000:06d}"


def mail_link(address: str) -> str:
    """The verification link Authentik mailed to `address`, read from Mailpit."""
    import re

    for _ in range(20):
        with urllib.request.urlopen(f"{MAILPIT}/api/v1/search?query=to:{urllib.parse.quote(address)}", timeout=10) as response:
            messages = json.load(response)["messages"]
        if messages:
            with urllib.request.urlopen(f"{MAILPIT}/api/v1/message/{messages[0]['ID']}", timeout=10) as response:
                text = json.load(response)["Text"]
            return re.search(r"https://\S+/if/flow/\S+", text).group(0)  # type: ignore[union-attr]
        time.sleep(1)
    raise AssertionError(f"no mail to {address} in Mailpit ({MAILPIT})")


def scope_mapping_email(pk: str, user_pk: int) -> dict[str, Any]:
    """The claims of the `email` scope mapping for a user, through Authentik's test endpoint."""
    status, _, body = call(
        opener(),
        f"{BASE}/api/v3/propertymappings/all/{pk}/test/",
        data={"user": user_pk},
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    check(status == 200, "scope mapping test endpoint answers")
    result = json.loads(body)["result"]
    try:
        return json.loads(result)
    except ValueError:
        return ast.literal_eval(result)


def delete(path: str) -> None:
    request = urllib.request.Request(f"{BASE}/api/v3/{path}", method="DELETE", headers={"Authorization": f"Bearer {TOKEN}"})
    try:
        opener().open(request, timeout=20)
    except urllib.error.HTTPError:
        pass


def verify_enrollment() -> None:
    """Closed enrollment: an invitation, a verified email and a second factor are required."""
    tag = secrets.token_hex(3)
    username, email, password = f"enroll-{tag}", f"enroll-{tag}@example.test", "Qa-passw0rd-long-enough!"
    admin = {"Authorization": f"Bearer {TOKEN}"}
    anonymous = opener()
    open_flow = challenge(anonymous, executor(anonymous, "default-enrollment-flow"))
    check(open_flow.get("component") == "ak-stage-access-denied", "enrollment without an invitation is refused (the stack has AUTHENTIK_ENROLLMENT_OPEN=false)")
    status, _, body = call(opener(), f"{BASE}/api/v3/stages/invitation/invitations/", data={"name": f"verify-{tag}", "single_use": True, "fixed_data": {"email": email}}, headers=admin)
    check(status == 201, "operator creates an invitation")
    invitation = json.loads(body)["pk"]
    try:
        enroll(invitation, username, email, password)
    finally:
        # Clean up the test person and the invitation, also after a failed check.
        for user in api(f"core/users/?username={username}")["results"]:
            delete(f"core/users/{user['pk']}/")
        delete(f"stages/invitation/invitations/{invitation}/")


def enroll(invitation: str, username: str, email: str, password: str) -> None:
    admin = {"Authorization": f"Bearer {TOKEN}"}
    client = opener()
    url = executor(client, "default-enrollment-flow", f"itoken={invitation}")
    current = challenge(client, url)
    check(current.get("component") == "ak-stage-prompt", "the invitation opens the enrollment form")
    challenge(client, url, {"component": "ak-stage-prompt", "username": username, "password": password, "password_repeat": password})
    current = challenge(client, url, {"component": "ak-stage-prompt", "name": "Enrollment Test", "email": email})
    check(current.get("component") == "ak-stage-email", "a verification email is sent")
    link = mail_link(email)
    check("flow_token=" in link, "the email carries a verification link")
    url = executor(client, "default-enrollment-flow", urllib.parse.urlsplit(link).query)
    current = challenge(client, url)
    seen_second_factor = False
    for _ in range(10):
        component = current.get("component")
        if component == "ak-stage-consent":
            current = challenge(client, url, {"component": component, "token": current["token"]})
        elif component == "ak-stage-authenticator-validate":
            totp_stage = next(stage for stage in current["configuration_stages"] if "totp" in stage["name"].lower())
            current = challenge(client, url, {"component": component, "selected_stage": totp_stage["pk"]})
        elif component == "ak-stage-authenticator-totp":
            seen_second_factor = True
            secret = base32_secret(current["config_url"])
            current = challenge(client, url, {"component": component, "code": totp_for(secret, int(time.time() // 30))})
        else:
            break
    check(seen_second_factor, "enrollment forces the person to set up a second factor")
    check(current.get("component") == "xak-flow-redirect", "enrollment then signs the person in")
    status, _, _ = call(client, f"{BASE}/api/v3/core/users/me/", headers={"Accept": "application/json"})
    check(status == 200, "the new person has a session")
    users = api(f"core/users/?username={username}")["results"]
    check(len(users) == 1, "the enrolled person exists")
    user = users[0]
    check(user["attributes"].get("shadow_verified_email") == email, "the verified ADDRESS is recorded")
    mapping = next(m for m in api("propertymappings/all/?search=" + urllib.parse.quote("Shadow verified email"))["results"])
    check(scope_mapping_email(mapping["pk"], user["pk"]).get("email_verified") is True, "the email scope reports the verified address as verified")
    # An address changed after verification is no longer verified.
    patch = urllib.request.Request(f"{BASE}/api/v3/core/users/{user['pk']}/", method="PATCH", data=json.dumps({"email": f"other-{email}"}).encode(), headers=admin | {"Content-Type": "application/json"})
    opener().open(patch, timeout=20)
    check(scope_mapping_email(mapping["pk"], user["pk"]).get("email_verified") is False, "a changed address is no longer reported as verified")


def main() -> None:
    client = opener()

    # 1. Discovery of the web provider (public issuer, end-session endpoint).
    status, _, body = call(client, f"{BASE}/application/o/shadow/.well-known/openid-configuration")
    check(status == 200, "web provider discovery answers 200")
    discovery = json.loads(body)
    check(discovery["issuer"] == f"{BASE}/application/o/shadow/", "issuer is the public per-provider issuer")
    check(discovery["end_session_endpoint"].endswith("/application/o/shadow/end-session/"), "end-session endpoint advertised")
    check("RS256" in discovery["id_token_signing_alg_values_supported"], "RS256 ID token signing")

    # 2. Declared provider and application.
    providers = {p["client_id"]: p for p in api("providers/oauth2/")["results"]}
    web = providers.get(CLIENT_ID)
    check(web is not None, "web provider exists")
    assert web is not None
    check(web["client_type"] == "confidential" and web["sub_mode"] == "hashed_user_id" and web["issuer_mode"] == "per_provider", "web provider is confidential, hashed_user_id, per_provider")
    check([u["url"] for u in web["redirect_uris"] if u["redirect_uri_type"] == "authorization"] == [REDIRECT_URI], "exact authorization redirect URI only")
    check({a["slug"] for a in api("core/applications/")["results"]} >= {"shadow"}, "application shadow exists")

    # 3. Strong authentication: the password alone does not sign in.
    first = opener()
    stalled = sign_in(first, "dev-admin", with_second_factor=False)
    check(stalled.get("component") == "ak-stage-authenticator-validate", "password alone stops at the second-factor stage")
    second = opener()
    done = sign_in(second, "dev-admin", with_second_factor=True)
    check(done.get("component") == "xak-flow-redirect", "password plus TOTP completes the sign-in")

    # 4. Authorization code with PKCE for the web client, then the token exchange.
    verifier = secrets.token_urlsafe(48)
    challenge_value = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    query = urllib.parse.urlencode(
        {
            "client_id": CLIENT_ID,
            "response_type": "code",
            "scope": "openid profile email",
            "redirect_uri": REDIRECT_URI,
            "state": secrets.token_urlsafe(16),
            "nonce": secrets.token_urlsafe(16),
            "code_challenge": challenge_value,
            "code_challenge_method": "S256",
        }
    )
    # Signed in, the implicit-consent provider answers the authorize request with a
    # redirect to the registered redirect URI carrying the code.
    status, headers, _ = call(second, f"{BASE}/application/o/authorize/?{query}")
    check(status in (301, 302), "authorize endpoint redirects a signed-in user")
    location = urllib.parse.urlsplit(headers["Location"])
    check(f"{location.scheme}://{location.netloc}{location.path}" == REDIRECT_URI, "redirect goes to the exact redirect URI")
    code = urllib.parse.parse_qs(location.query)["code"][0]
    status, _, body = call(
        opener(),
        discovery["token_endpoint"],
        form={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": verifier,
        },
        headers={"Authorization": "Basic " + base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()},
    )
    check(status == 200, "token endpoint accepts the code, PKCE verifier and client secret")
    tokens = json.loads(body)
    claims = json.loads(base64.urlsafe_b64decode(tokens["id_token"].split(".")[1] + "=="))
    check(claims["iss"] == discovery["issuer"] and claims["aud"] == CLIENT_ID, "ID token issuer and audience")
    check(claims["email"] == "admin@example.local" and claims["email_verified"] is True, "ID token carries the verified email")
    if "--enrollment" in sys.argv:
        verify_enrollment()
    print("Authentik local setup verified.")


if __name__ == "__main__":
    main()
