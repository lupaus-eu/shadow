# Ticket 02: Authentik provider for MCP (from 080H)

Status: implemented

## Goal

Authentik has the dedicated, pre-registered MCP provider and application "Shadow MCP", and a real MCP client signs in through it; no Shadow code uses it yet.

## Implementation

- Blueprint `authentik/blueprints/shadow-mcp-application.yaml` (design table), added to `configure.sh` and the configuration fingerprint; env `MCP_OIDC_CLIENT_ID`, `MCP_OIDC_CLIENT_SECRET`, `MCP_OIDC_ISSUER` in `.env.example` and compose (the issuer is read in step 3b).
- Script `scripts/verify-authentik-local.py`: checks web and MCP discovery documents and JWKS, that the two issuers differ, and the declared redirect URIs, through the Authentik API.
- Real sign-in demonstration (QA evidence): Claude Code with `claude mcp add --transport http --client-id … --client-secret --callback-port <port>` and MCP Inspector against a stub protected resource or the existing `/api/mcp` metadata; decode the access token and record that `aud` equals the client id and `iss` the MCP issuer. The claude.ai connector and the claude.com callback cannot be tested locally and are recorded as such.
- `docs/runbooks/authentik-local.md` section on the MCP provider (client id and secret, adding a redirect URI, secret rotation).
- Not done: verifying MCP tokens in the backend, tenant binding, removal of the old OAuth server (steps 080I–K); MCP clients keep using today's OAuth server.

## Acceptance criteria

- [x] The blueprint creates a confidential provider and application "Shadow MCP" with strict redirect URIs for claude.ai and claude.com, the loopback regex for `http://localhost|127.0.0.1:<port>/callback` and `/oauth/callback` (Claude Code, MCP Inspector), explicit consent every time (own authorization flow), PKCE with S256 enforced by a policy, `sub_mode: hashed_user_id`, `per_provider` issuer, scopes `openid profile offline_access`; dynamic registration is off.
- [x] `scripts/verify-authentik-local.py` passes against the local stack.
- [x] A scripted authorization-code sign-in with a pre-registered client succeeds for a dev user (consent, loopback code with PKCE) and yields an access and refresh token whose `aud` is the MCP client id and `iss` the MCP issuer, different from the web issuer; web-provider tokens carry another audience. **A real client (Claude Code, MCP Inspector) was not run**: it needs an interactive browser; recorded as open in the QA checklist, to do before step 3b.
- [x] No failure was found with the scripted client; if a real client cannot use the provider, that is a decision request (public client or facade), not worked around silently.

## Testing

- [x] Authentik — verify script; sign-in demonstration as QA evidence in `docs/operations/qa/AI-MCP-QA-CHECKLIST.md`
- [x] Backend/Frontend — not applicable (no application code)

## Ajetut tarkistukset

- [x] `python3 scripts/verify-authentik-local.py` (kokonainen ajo, toistettu) oikeaa stackia vasten (Authentik 2026.8.5, Caddy `id.app.localhost`): MCP-providerin asetukset ja redirect-URI:t, discovery, RFC 8414 -metadata, JWKS, ei dynaamista rekisteröintiä, kymmenen rekisteröimätöntä redirect-URI:a evätään 400:lla, loopback hyväksytään, PKCE S256 pakollinen (ei challengea / plain evätään), consent joka kerta, koodi loopbackiin, token (`aud` = client id, `iss` = MCP-issuer ≠ web-issuer), refresh-rotaatio (vanha evätään), koodia ei voi käyttää kahdesti, väärä secret `invalid_client`, koodi evätään ilman verifieria ja väärällä verifierilla, web-providerin tokenit eivät kanna MCP-audienssia.
- [x] `authentik-config-init`: exit 0, "Authentik configuration check passed" (MCP-sovellus tarkistetaan).
- Ei ajettu: oikea MCP-client (Claude Code, MCP Inspector) — vaatii interaktiivisen selaimen, CLI ei ole automaatioympäristössä; claude.ai-connector ja claude.com-callback — ei testattavissa paikallisesti. Kirjattu `AI-MCP-QA-CHECKLIST.md`:iin avoimeksi.

## AI review

- [x] Tuore subagentti (opus), taso medium–high, 1 kierros; tarkisti myös Authentikin lähdekoodin (regex-täsmäys `fullmatch`, ei ohitusta; DCR pois). Löydökset:
  1. medium, PKCE ei ollut pakollinen (dokumentaatio väitti) — **fixed** (expression policy vaatii S256:n sekä MCP- että web-sovellukselle; negatiiviset testit). Token-päätepiste ei sido `redirect_uri`:a koodin antaneeseen URI:in — **accepted risk** (Authentik; PKCE ja kertakäyttöinen koodi rajaavat).
  2. medium, redirect-URI-evätestit eivät voineet epäonnistua — **fixed** (vaaditaan 400 ja ei `Location`; kymmenen tapausta, positiivinen kontrolli).
  3. low, consent muistettiin 4 viikkoa jaetussa stagessa — **fixed** (oma authorization flow, consent `always_require`).
  4. low, skripti poisti kaikki consentit — **fixed** (siivous poistettu, ei tarvita).
  5. low, väärän secretin ja rotaation testit heikkoja — **fixed** (`invalid_client`, vanha refresh evätään, PKCE-negatiivit).
  6. low, Claude Code -ohje ei vielä osu Authentikiin (`/api/mcp` mainostaa vielä omaa OAuth-palvelinta) — **fixed** (runbookissa: toimii vaiheesta 3b, siihen asti stub-resurssi).
  7. low, kriteerit ja dokumentit — **fixed** (skriptin nimi, regexin sanamuoto, `MCP_OIDC_ISSUER` tuotantosopimukseen); web-tokenin audienssitesti lisätty; **oikea client -kriteeri jätetty auki rehellisesti** (ei suljettu täytetyksi).
  Ei toista kierrosta; korjaukset varmistettu stackin uudelleenajolla (skripti läpi). Yksi kierros kolmesta.

## Documentation effects

- [x] Update `docs/operations/` or `docs/runbooks/` — `docs/runbooks/authentik-local.md`, `docs/operations/qa/AI-MCP-QA-CHECKLIST.md`
- [x] Update architecture or ADR — `docs/adr/0023-…` (scripted verification; real client still open), `docs/architecture/deployment.md` (`MCP_OIDC_ISSUER`)
- [x] Update `.env.example`

## Blocked by

- 01

## Completion record

- MCP-provider "Shadow MCP" (blueprint, oma authorization flow ja pakotettu consent, PKCE-policy), verifiointi skriptillä ja dokumentit valmiit. Poikkeamat: PKCE vaaditaan policylla (Authentik ei tarjoa asetusta), oma consent-flow `always_require`, loopback-regex kattaa myös `/oauth/callback`, verifiointi esirekisteröidyn clientin simulaatiolla — oikean clientin kirjautuminen on edelleen auki. Commit: `feat: authentik-sign-in 02`.

## Comments

- Lähde: Yearclock `6848e72` (`authentik/`, `docker-compose.yml`, `docs/runbooks/authentik-*.md`, `backend/app/oidc.py`); kirjaa käytetyt lähdetiedostot lopussa.
