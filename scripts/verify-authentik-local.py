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
  token endpoint answers with an ID token whose email is verified (`email_verified`);
* the MCP provider (ADR-0023): declared settings and redirect URIs, discovery and JWKS,
  explicit consent, a pre-registered client's authorization code with PKCE yielding an
  access token whose audience is the MCP client id and whose issuer is the MCP issuer
  (not the web issuer), a refresh grant, and refusal of an unregistered redirect URI.

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
MCP_CLIENT_ID = os.getenv("MCP_OIDC_CLIENT_ID", "shadow-mcp-local")
MCP_CLIENT_SECRET = os.getenv("MCP_OIDC_CLIENT_SECRET", "replace-with-a-random-mcp-secret")
# A loopback callback of a local client (Claude Code pins its port with --callback-port).
MCP_LOOPBACK_REDIRECT = "http://localhost:33418/callback"
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
    built = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar),
        urllib.request.HTTPSHandler(context=context),
        NoRedirect(),
    )
    built._jar_cookies = lambda: list(jar)  # type: ignore[attr-defined]
    return built


def call(
    client: urllib.request.OpenerDirector,
    url: str,
    *,
    data: dict[str, Any] | None = None,
    form: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    body = None
    # Authentik's CSRF check on HTTPS wants a Referer and its own CSRF cookie echoed in a header.
    all_headers = {"Referer": f"{BASE}/"} | dict(headers or {})
    for cookie in getattr(client, "_jar_cookies", lambda: [])():
        if cookie.name == "authentik_csrf":
            all_headers.setdefault("X-authentik-CSRF", cookie.value)
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


def jwt_claims(token: str) -> dict[str, Any]:
    return json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))


def verify_mcp(signed_in: urllib.request.OpenerDirector, web_issuer: str) -> None:
    """The dedicated MCP provider (ADR-0023), exercised as a pre-registered client would."""
    providers = {p["client_id"]: p for p in api("providers/oauth2/")["results"]}
    mcp = providers.get(MCP_CLIENT_ID)
    check(mcp is not None, "MCP provider exists")
    assert mcp is not None
    check(mcp["client_type"] == "confidential" and mcp["sub_mode"] == "hashed_user_id" and mcp["issuer_mode"] == "per_provider", "MCP provider is confidential, hashed_user_id, per_provider")
    check(sorted(mcp["grant_types"]) == ["authorization_code", "refresh_token"], "only the authorization code and refresh token grants")
    uris = {(u["matching_mode"], u["url"]) for u in mcp["redirect_uris"]}
    check(("strict", "https://claude.ai/api/mcp/auth_callback") in uris and ("strict", "https://claude.com/api/mcp/auth_callback") in uris, "strict redirect URIs for claude.ai and claude.com")
    check(sum(1 for mode, _ in uris if mode == "regex") == 1 and len(uris) == 3, "one loopback pattern and no other redirect URI")
    check("shadow-mcp" in {a["slug"] for a in api("core/applications/?superuser_full_list=true")["results"]}, "application shadow-mcp exists")

    status, _, body = call(opener(), f"{BASE}/application/o/shadow-mcp/.well-known/openid-configuration")
    check(status == 200, "MCP discovery answers 200")
    discovery = json.loads(body)
    mcp_issuer = f"{BASE}/application/o/shadow-mcp/"
    check(discovery["issuer"] == mcp_issuer and mcp_issuer != web_issuer, "the MCP issuer differs from the web issuer")
    check("registration_endpoint" not in discovery, "dynamic client registration is not offered")
    status, _, _ = call(opener(), discovery["jwks_uri"])
    check(status == 200, "MCP JWKS is served")
    status, _, _ = call(opener(), f"{BASE}/.well-known/oauth-authorization-server/application/o/shadow-mcp/")
    check(status == 200, "RFC 8414 authorization server metadata is served for the MCP issuer")

    verifier = secrets.token_urlsafe(48)
    challenge_value = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()

    def authorize_query(redirect_uri: str) -> str:
        return urllib.parse.urlencode(
            {
                "client_id": MCP_CLIENT_ID,
                "response_type": "code",
                "scope": "openid profile offline_access",
                "redirect_uri": redirect_uri,
                "state": secrets.token_urlsafe(16),
                "code_challenge": challenge_value,
                "code_challenge_method": "S256",
            }
        )

    # An unregistered redirect URI is refused outright (HTTP 400, no redirect), including the
    # cases a loose pattern would let through; the loopback URI gets a redirect (control).
    for bad in (
        "https://evil.example/callback",
        "https://claude.ai/api/mcp/auth_callback/extra",
        "https://claude.ai/api/mcp/auth_callback?x=1",
        "http://localhost:33418/other",
        "http://localhost:33418/callback/",
        "http://localhost:33418/callback?x=1",
        "http://localhost:abc/callback",
        "https://localhost:33418/callback",
        "http://evil.localhost.example:33418/callback",
        "http://localhost:1@evil.example/callback",
    ):
        status, headers, _ = call(signed_in, f"{BASE}/application/o/authorize/?{authorize_query(bad)}")
        check(status == 400 and "Location" not in headers, f"unregistered redirect URI is refused with 400: {bad}")
    status, headers, _ = call(signed_in, f"{BASE}/application/o/authorize/?{authorize_query(MCP_LOOPBACK_REDIRECT)}")
    check(status in (301, 302), "the registered loopback redirect URI is accepted (control)")

    # PKCE with S256 is required: no challenge and the plain method are refused.
    base_query = {"client_id": MCP_CLIENT_ID, "response_type": "code", "scope": "openid profile offline_access", "redirect_uri": MCP_LOOPBACK_REDIRECT, "state": "s"}
    for label, extra in (("no code_challenge", {}), ("the plain method", {"code_challenge": "x" * 43, "code_challenge_method": "plain"})):
        status, headers, body = call(signed_in, f"{BASE}/application/o/authorize/?{urllib.parse.urlencode(base_query | extra)}")
        location = headers.get("Location", "")
        denied = status >= 400 or ("explicit-consent" not in location and "shadow-mcp-authorization" not in location and "code=" not in location)
        check(denied and "code=" not in location, f"authorization without PKCE S256 is refused ({label})")

    # Explicit consent, then the code at the loopback redirect (the regex pattern).
    query = authorize_query(MCP_LOOPBACK_REDIRECT)
    status, headers, _ = call(signed_in, f"{BASE}/application/o/authorize/?{query}")
    check(status in (301, 302) and "shadow-mcp-authorization" in headers["Location"], "authorization goes through the MCP authorization flow with its own consent")
    flow_slug = urllib.parse.urlsplit(headers["Location"]).path.rstrip("/").split("/")[-1]
    url = executor(signed_in, flow_slug, query)
    current = challenge(signed_in, url)
    check(current.get("component") == "ak-stage-consent", "the consent stage is shown")
    current = challenge(signed_in, url, {"component": "ak-stage-consent", "token": current["token"]})
    check(current.get("component") == "xak-flow-redirect" and current["to"].startswith(MCP_LOOPBACK_REDIRECT + "?"), "consent redirects to the loopback callback with a code")
    code = urllib.parse.parse_qs(urllib.parse.urlsplit(current["to"]).query)["code"][0]
    auth = {"Authorization": "Basic " + base64.b64encode(f"{MCP_CLIENT_ID}:{MCP_CLIENT_SECRET}".encode()).decode()}
    status, _, body = call(
        opener(),
        discovery["token_endpoint"],
        form={"grant_type": "authorization_code", "code": code, "redirect_uri": MCP_LOOPBACK_REDIRECT, "code_verifier": verifier},
        headers=auth,
    )
    check(status == 200, "token endpoint accepts the pre-registered client's code, PKCE verifier and secret")
    tokens = json.loads(body)
    access = jwt_claims(tokens["access_token"])
    check(access["aud"] == MCP_CLIENT_ID, "access token audience is the MCP client id")
    check(access["iss"] == mcp_issuer and access["iss"] != web_issuer, "access token issuer is the MCP issuer, not the web issuer")
    check(bool(tokens.get("refresh_token")), "a refresh token is issued (offline_access)")
    status, _, body = call(opener(), discovery["token_endpoint"], form={"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"]}, headers=auth)
    check(status == 200 and json.loads(body).get("access_token"), "the refresh grant works")
    rotated = json.loads(body)
    check(rotated.get("refresh_token") not in (None, tokens["refresh_token"]), "the refresh token is rotated")
    status, _, _ = call(opener(), discovery["token_endpoint"], form={"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"]}, headers=auth)
    check(status == 400, "the old refresh token is refused after rotation")
    status, _, _ = call(opener(), discovery["token_endpoint"], form={"grant_type": "authorization_code", "code": code, "redirect_uri": MCP_LOOPBACK_REDIRECT, "code_verifier": verifier}, headers=auth)
    check(status == 400, "an authorization code cannot be used twice")
    wrong = {"Authorization": "Basic " + base64.b64encode(f"{MCP_CLIENT_ID}:wrong-secret".encode()).decode()}
    status, _, body = call(opener(), discovery["token_endpoint"], form={"grant_type": "refresh_token", "refresh_token": rotated["refresh_token"]}, headers=wrong)
    check(status in (400, 401) and json.loads(body).get("error") == "invalid_client", "a wrong client secret is refused as invalid_client")

    # A code is bound to its PKCE challenge: without the verifier, or with another, it is refused.
    for label, verifier_value in (("without a verifier", None), ("with a wrong verifier", secrets.token_urlsafe(48))):
        fresh_verifier = secrets.token_urlsafe(48)
        fresh_challenge = base64.urlsafe_b64encode(hashlib.sha256(fresh_verifier.encode()).digest()).rstrip(b"=").decode()
        fresh_query = urllib.parse.urlencode(base_query | {"code_challenge": fresh_challenge, "code_challenge_method": "S256"})
        status, headers, _ = call(signed_in, f"{BASE}/application/o/authorize/?{fresh_query}")
        flow = urllib.parse.urlsplit(headers["Location"]).path.rstrip("/").split("/")[-1]
        furl = executor(signed_in, flow, fresh_query)
        step = challenge(signed_in, furl)
        step = challenge(signed_in, furl, {"component": "ak-stage-consent", "token": step["token"]})
        fresh_code = urllib.parse.parse_qs(urllib.parse.urlsplit(step["to"]).query)["code"][0]
        form = {"grant_type": "authorization_code", "code": fresh_code, "redirect_uri": MCP_LOOPBACK_REDIRECT}
        if verifier_value is not None:
            form["code_verifier"] = verifier_value
        status, _, _ = call(opener(), discovery["token_endpoint"], form=form, headers=auth)
        check(status == 400, f"a code is refused {label}")


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
    check(web["grant_types"] == ["authorization_code"], "web provider allows only the authorization code grant")
    check(web["client_type"] == "confidential" and web["sub_mode"] == "hashed_user_id" and web["issuer_mode"] == "per_provider", "web provider is confidential, hashed_user_id, per_provider")
    check([u["url"] for u in web["redirect_uris"] if u["redirect_uri_type"] == "authorization"] == [REDIRECT_URI], "exact authorization redirect URI only")
    check({a["slug"] for a in api("core/applications/?superuser_full_list=true")["results"]} >= {"shadow"}, "application shadow exists")

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
    check(claims["aud"] != MCP_CLIENT_ID and jwt_claims(tokens["access_token"])["aud"] != MCP_CLIENT_ID, "web provider tokens do not carry the MCP audience (the MCP verifier refuses them)")
    verify_mcp(second, discovery["issuer"])
    if "--enrollment" in sys.argv:
        verify_enrollment()
    print("Authentik local setup verified.")


if __name__ == "__main__":
    main()
