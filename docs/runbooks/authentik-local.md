# Local Authentik setup

This runbook completes the local identity configuration supplied by Docker Compose. Authentik owns registration, email verification, credentials, passkeys, MFA, recovery, and its own identity sessions. Shadow receives only verified OpenID Connect identity claims.

## 1. Set local secrets

Copy `.env.example` to `.env` and replace at least:

- `AUTHENTIK_POSTGRES_PASSWORD`
- `AUTHENTIK_SECRET_KEY`
- `AUTHENTIK_BOOTSTRAP_PASSWORD`
- `OIDC_CLIENT_SECRET`

Keep `OIDC_CLIENT_SECRET` identical for the Shadow backend and the mounted Authentik blueprint. Never commit `.env`.

## 2. Start and initialize

```bash
docker compose up --build
```

Open `http://localhost:8190/if/flow/initial-setup/` including the trailing slash. Sign in as `akadmin`. The mounted `shadow-application.yaml` blueprint creates the confidential Shadow OIDC provider and application automatically. The provider allows only the authorization-code grant used by the backend.

Confirm the provider discovery document:

```text
http://localhost:8190/application/o/shadow/.well-known/openid-configuration
```

## 3. Identity flow policy

The one-shot `authentik-config-init` service applies the pinned image's
verified-email enrollment and email-plus-MFA recovery flows before the
Shadow backend starts. It then applies the versioned Shadow policy:

- password login always requires an enrolled TOTP or WebAuthn factor;
- a user without a factor must configure one before login can finish;
- WebAuthn uses required user verification and a resident credential so it
  works as a passkey;
- the Identification stage offers passkey autofill as the preferred path;
- recovery requires both the delivered email link and an existing MFA factor;
- successful enrollment email verification records a dedicated verification
  fact, and only identities carrying that fact receive `email_verified: true`.

The policy files are under `authentik/blueprints/`, and the ordered bootstrap
is `authentik/configure.sh`. Do not weaken the validation stage to
password-only access.

Configure the Scaleway SMTP values in `.env` before testing enrollment or
recovery. Identity email credentials belong only to Authentik and remain
separate from later Shadow transactional-email credentials.

## Legal links on the sign-in pages

Authentik 2026.8 takes the footer links of its flow pages from the system setting **Footer links**, not from the
brand, so `shadow-brand.yaml` cannot carry them. **Human:** in the Authentik admin interface open
System > Settings and set Footer links to `[{"name": "Terms and privacy", "href": "https://<app domain>/legal"}]`
(a Finnish name is fine). Not yet confirmed on 2026.8.5 against a running instance; check the page after setting it.

## Sign-in page look

The sign-in pages use the web application's stylesheet (ADR-0039). Locally the stylesheet comes from the Vite
dev server (`AUTHENTIK_THEME_CSS_URL`, default `http://localhost:8173/src/theme.css?direct`), so start the
frontend (`make up` does) to see the application's colors; without it the pages show the bridge's fallback colors.
The dev server's stylesheet has no font rules, so locally the pages use the system font; production uses Inter.
After changing `authentik/blueprints/shadow-brand.css` run `docker compose up -d authentik-config-init`
(`make authentik-apply` in production) and reload the page.

## Enrollment invitations

Locally `AUTHENTIK_ENROLLMENT_OPEN=true` (the default in `docker-compose.yml`)
lets anyone enroll. Production sets it to `false`, so the enrollment flow starts
with an invitation stage and only people with an invitation link from the
operator can create an account. To try the closed mode locally, start the
Authentik services with `AUTHENTIK_ENROLLMENT_OPEN=false`; the operator guide is
[authentik-invitations.md](authentik-invitations.md).

## 4. Acceptance check

Use a non-admin test identity and verify:

- enrollment requires a delivered verification link;
- a passkey can be enrolled and used to sign in;
- password sign-in cannot finish without a second factor;
- the recovery flow requires email plus the configured MFA check;
- Shadow opens its authenticated English shell;
- switching to Finnish survives a reload;
- logout returns to the signed-out Shadow entry point;
- deleting or expiring the Authentik session causes Shadow access to fail closed after its local session expires or is revoked through configured OIDC logout.

The Authentik container version is pinned. Review its release notes and re-run this checklist before changing that version.

## Primary references

- [Authentik Docker Compose installation](https://docs.goauthentik.io/install-config/install/docker-compose/)
- [Authentik OAuth2/OIDC provider](https://docs.goauthentik.io/add-secure-apps/providers/oauth2/)
- [Authentik example flows](https://docs.goauthentik.io/add-secure-apps/flows-stages/flow/examples/flows/)
- [Authentik WebAuthn/passkey setup](https://docs.goauthentik.io/add-secure-apps/flows-stages/stages/authenticator_webauthn/)
- [Authentik blueprints](https://docs.goauthentik.io/customize/blueprints)
