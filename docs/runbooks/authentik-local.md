# Local Authentik setup

Authentik is Shadow's identity provider (ADR-017). It owns registration, email
verification, credentials, passkeys, MFA, recovery and its own identity sessions.
The backend receives only verified OpenID Connect identity claims. This runbook
covers the local stack; production comes with step 086A of the SaaS plan.

## 1. Start

Copy `.env.example` to `.env` (the local values work as they are) and start the
stack. The first start generates the local TLS material for `app.localhost` and
`id.app.localhost`; trust the CA the script prints in your browser or system, once:

```bash
make dev-up
```

The services are `authentik-db-init` (creates the `authentik` role and database in
the application's PostgreSQL), `authentik-server`, `authentik-worker` and the
one-shot `authentik-config-init`, which applies the blueprints. Authentik is
reachable only through Caddy at `https://id.app.localhost`. Authentik mail
(enrollment, recovery) goes to Mailpit at `http://localhost:8025`.

Authentik 2026.8.5 runs on the application's PostgreSQL 18 container (verified
2026-11-06); it uses its own logical database and role. The local network now reserves
`172.28.59.2`–`.15` for fixed addresses; if `make dev-up` complains about the network,
run `make dev-down` first so Compose recreates it.

The administrator is `akadmin` with `AUTHENTIK_BOOTSTRAP_PASSWORD` from `.env`
(`https://id.app.localhost/if/admin/`).

## 2. What the blueprints create

All in `authentik/blueprints/`, applied in order by `authentik/configure.sh`:

| Blueprint | Creates |
| --- | --- |
| `shadow-identity-flows.yaml` | Enrollment behind an invitation (when `AUTHENTIK_ENROLLMENT_OPEN=false`) with email verification and a mandatory second factor, sign-in that always needs TOTP or a passkey, recovery by email plus a factor |
| `shadow-application.yaml` | The confidential OIDC provider and application `shadow` for the backend (client id `LOCAL_OIDC_CLIENT_ID`, exact redirect `LOCAL_OIDC_REDIRECT_URI`) and the `email` scope: `email_verified` is true only while the user's address equals the address recorded as verified |
| `shadow-brand.yaml` | The title and colours of the sign-in pages and the recovery flow |
| `authentik/dev/shadow-dev-users.yaml` and `provision-dev-totp.py` | Development users only, mounted only by the local Compose project |

`authentik/apply-tenant-settings.py` then turns off self-service changes of email and username and impersonation (a blueprint cannot change tenants). After applying, `authentik/verify-config.py` checks that the essentials exist (the
application, the invitation and second-factor stages on enrollment, forced second-factor
setup at sign-in); a failed check fails the run, which is then retried. The apply is
skipped when nothing that feeds it changed (the blueprints, the image version, the
values the blueprints read). To apply anyway (for
example after an interface change you want to undo):

```bash
make authentik-apply
```

Do not weaken the sign-in validation stage to password-only access.

## 3. Development users

| User | Email (links to the seeded account) |
| --- | --- |
| `dev-admin` | `admin@example.local` |
| `dev-consultant` | `consultant@example.local` |

The password is `AUTHENTIK_DEV_USER_PASSWORD` (`.env.example`). Multi-factor
stays enforced: each user has a TOTP device with the RFC 6238 test secret
`GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ`. Add it to an authenticator app, or print the
current code:

```bash
python3 - <<'PY'
import hmac, hashlib, struct, time
d = hmac.new(b"12345678901234567890", struct.pack(">Q", int(time.time()//30)), hashlib.sha1).digest()
o = d[-1] & 15
print(f"{(struct.unpack('>I', d[o:o+4])[0] & 0x7fffffff) % 1000000:06d}")
PY
```

These values exist only for local development and must never be used elsewhere.

## 4. Enrollment

Locally `AUTHENTIK_ENROLLMENT_OPEN=true` lets anyone enroll. Production sets it to
`false`: enrollment then needs an invitation (see
[authentik-invitations.md](authentik-invitations.md)). To try the closed mode,
set `AUTHENTIK_ENROLLMENT_OPEN=false` in `.env` and apply the blueprints
(command above).

## 5. Verify

With the stack up, the script checks the discovery document, the declared providers,
that a password alone does not sign in, the authorization-code flow with PKCE and the
ID token's verified email:

```bash
python3 scripts/verify-authentik-local.py
```

With enrollment closed it also checks the invitation, the verification email, the
forced second factor and the recorded verified email:

```bash
MAILPIT_URL=http://localhost:8025 python3 scripts/verify-authentik-local.py --enrollment
```

TOTP codes cannot be reused, so the script waits for the next 30-second step when it
runs twice in a row.

With the whole stack up, `make sign-in-verify` signs a seeded user in to Shadow through
Authentik (login redirect, password and TOTP, code to the callback, session linked to the
seeded account), signs out (both sessions end and the browser returns to `/login`), and
checks that a person whose address is no longer verified, and a verified person Shadow does
not know, are refused without a session.

## 6. MCP provider

Authentik signs AI clients in through a dedicated provider, "Shadow MCP" (ADR-0023;
`authentik/blueprints/shadow-mcp-application.yaml`, application slug `shadow-mcp`). It is a
confidential, pre-registered client: the person who connects an AI tool is given the
client id and secret. The backend does not use it yet (token verification arrives in step
3b of the SaaS plan); until then MCP clients keep using today's OAuth server.

| Setting | Meaning |
| --- | --- |
| `MCP_OIDC_CLIENT_ID` | The client id. It is the audience of every access token this provider issues. |
| `MCP_OIDC_CLIENT_SECRET` | A long random secret, shared by all companies (it does not separate them; membership does). Never commit it; production keeps it in the protected env file. |
| `MCP_OIDC_ISSUER` | `https://<identity host>/application/o/shadow-mcp/`, read by the backend in step 3b. |

The provider allows only the authorization code and refresh token grants, requires PKCE
with S256 (an expression policy refuses an authorization request without it, because the
secret is shared and PKCE is what ties a code to the client that asked), asks for consent
every time in its own authorization flow (Authentik's default flow remembers a consent for
four weeks), uses `hashed_user_id` subjects, and accepts exactly these redirect
URIs: `https://claude.ai/api/mcp/auth_callback`, `https://claude.com/api/mcp/auth_callback`
(strict) and a loopback pattern `http://localhost:<port>/callback` or
`/oauth/callback` (also `127.0.0.1`) for local clients. Dynamic client registration is not
offered. To allow another client, add its redirect URL to the blueprint (strict for a remote
client, never a wildcard) and run `make authentik-apply`. To change the secret, change
`MCP_OIDC_CLIENT_SECRET` and apply; everyone who connected must enter the new value, and
tokens already issued work until they expire.

Connect a client by hand:

- Claude Code: `claude mcp add --transport http --client-id "$MCP_OIDC_CLIENT_ID"
  --client-secret --callback-port 33418 shadow https://app.localhost/api/mcp`, then
  `/mcp` to sign in. Pin `--callback-port`; the redirect is `http://localhost:<port>/callback`.
- claude.ai custom connector: enter the client id and secret under Advanced settings; the
  callback `https://claude.ai/api/mcp/auth_callback` is registered.

Both need the MCP endpoint to name this provider as its authorization server, which it does
from step 3b of the SaaS plan: `/api/mcp` still advertises Shadow's own OAuth server today.
Before that, point a client at a stub protected resource whose metadata names
`https://id.app.localhost/application/o/shadow-mcp/`.

`make authentik-verify` exercises the provider as a pre-registered client would (consent every
time, loopback code with PKCE, a code refused without or with a wrong verifier, no PKCE or the
plain method refused, access and refresh token with rotation, audience and issuer, refusal of
unregistered redirect URIs with HTTP 400, a wrong secret refused). Signing in with a real MCP client is manual QA
(`docs/operations/qa/AI-MCP-QA-CHECKLIST.md`).

## 7. Operator cautions

- Removing a person's second-factor devices in the administration lets anyone who holds
  their password enroll a new factor at the next sign-in: verify the person's identity first.
- Deactivating a person removes their access; recovery does not reactivate them.
- Impersonation is turned off in the blueprints; operator access to a company's data goes
  through explicit support access (step 7 of the SaaS plan).

## 8. Cleaning up the earlier Authentik volumes

An earlier local Authentik setup left the volumes `authentik_data` and
`authentik_database_data` (declared in `docker-compose.yml` so that nothing deletes
them automatically). They are not used. After checking that you need nothing from
them, remove them yourself with `docker volume rm <project>_authentik_data
<project>_authentik_database_data`.

## 9. Acceptance check

Use a non-admin test identity: enrollment requires a delivered verification link;
a passkey can be enrolled and used; password sign-in cannot finish without a second
factor; recovery requires email plus a factor. The passkey step needs a browser
(or a virtual authenticator) and is not covered by the script.

## Primary references

- [Authentik OAuth2/OIDC provider](https://docs.goauthentik.io/add-secure-apps/providers/oauth2/)
- [Authentik example flows](https://docs.goauthentik.io/add-secure-apps/flows-stages/flow/examples/flows/)
- [Authentik blueprints](https://docs.goauthentik.io/customize/blueprints)
