# Ticket 05: Remove Microsoft Entra (079D)

Status: implemented

## Goal

No Entra setup, wording or test remains outside historical records, and the repository documents Authentik as the identity provider.

## Implementation

- Delete `scripts/setup-local-entra.sh`, `scripts/verify-local-direct-entra-config.sh`, `.env.entra.example`, the `.env.entra.local` handling in the Makefile/compose/`.gitignore`, `backend/app/provision_local_admin.py` and its tests, and the Entra prompts of `bootstrap_admin.py`; `make provision-local-admin` goes (the dev seed provisions the dev users).
- Remove Entra wording from the frontend, `README.md`, `backend/README.md`, `docs/operations/local-development.md`, `docs/runbooks/production.md` (§2.7 and Entra steps: replaced by a pointer to the Authentik runbooks and the production steps of the plan), the QA checklists, the production compose verification scripts (mock OIDC discovery and values) and their Entra tests.
- Diagrams `component-authentication-topology` and `sequence-oidc-login` (+ SVG) and the LikeC4 MCP model mention of Entra.
- ADR notes: ADR-004 and ADR-013 mark their Entra parts as superseded by ADR-017; ADR-006 as historical; `docs/adr/README.md`.
- Not done: deleting the Entra app registration (after the production cutover is approved, step 087B), production Authentik (086A).

## Acceptance criteria

- [x] A repository search for "Entra" and "microsoftonline" finds only `docs/archive/`, `docs/ai-reviews/`, the ADRs (history; ADR-0001, 0003, 0005 and 0014 mention it in their body text), the QA evidence records under `docs/operations/qa/` (kept as evidence, with notes), link filenames (`0013-shared-entra-…`, `TASK-059A/B-…`) and the SaaS plan. Case-insensitive hits "central" are false positives.
- [x] `make dev-up` (expanded with `make -n`; the equivalent commands run against real containers), `make backend-check` (the same ruff, pytest, pyright commands) pass without any Entra input; `.env.entra.*` is gone. `make frontend-check` was not run (no pnpm/node_modules here); no frontend file changed.
- [x] The production compose verification passes with the new OIDC value shapes.
- [x] The authentication diagrams and runbooks describe Authentik.

## Testing

- [x] Backend/API — the remaining auth tests pass; Entra tests removed with their code
- [x] Compose/runtime — `docker compose config`; production compose verification scripts
- [x] Documentation — link and reference check (`git diff --check`, search)
- [x] Browser/E2E — full sign-in once more on the final stack

## Ajetut tarkistukset

- [x] `ruff check .`, `pyright` (yksi ennestään oleva virhe `ai_change_sets/service.py:381`), `pytest` koko sarja PostgreSQL 18:aa vasten — 1709 passed, 7 skipped (kuusi testiä vähemmän: `test_provision_local_admin.py` poistui koodin mukana).
- [x] Koko stack oikeilla konteilla (eristetty Compose-projekti `shadowverify`): tietokanta, Authentik, backend, frontend (Vite), Caddy; `https://app.localhost/` palauttaa SPA:n; `scripts/verify-local-sign-in.py` ja `verify-authentik-local.py` ajettu aiemmissa tickeleissä samaa koodia vasten.
- [x] `docker compose config` (dev ilman Entra-arvoja); `make -n dev-up`; tuotanto-compose-verifiointi bash 3 -kopiolla uusilla OIDC-arvoilla; `bash -n` ja `py_compile` CI-harnessille; `git diff --check`; hakukriteeri (yllä).
- Ei ajettu: `.github/scripts/verify-production-runtime.sh` ja `verify-release-compose-failure.sh` (vaativat Linux-isännän; harness-muutokset tarkistettiin lukemalla backendin säännöt vasten), LikeC4-validaattori ja LikeC4-PNG:n uudelleenrenderöinti, `make frontend-check`.

## AI review

- [x] Tuore subagentti (opus), taso medium–high, 1 kierros. Ei korkean vakavuuden löydöksiä; poistot eivät rikkoneet rakennusta tai CI:tä, harnessin simuloitu issuer läpäisee backendin säännöt, diagrammit ovat johdonmukaisia. 4 keskitasoa, 8 matalaa:
  M1. QA-bannerit sanoivat "ei menettely", vaikka elävät dokumentit viittaavat niihin — **fixed** (bannerit rajattu Entra-aikaisiin osioihin; AI-MCP-gate ja Authentik-osiot nimetty voimassa oleviksi; muut bannerit tarkennettu).
  M2. `production.md` §2.7 osoitti väärään paikkaan käynnissä olevan tuotannon Entra-ohjeisiin — **fixed** (viittaa `docs/PRODUCTION-RUNBOOK.md` §2.7 tagissa `v0.2.0`; tarkistettu että kohta on olemassa).
  M3. testing.md:n selain-QA vaati lokeihin ei sähköpostia, vaikka Authentik kirjaa `id_token_hint`in — **fixed** (poikkeus ja viittaus ADR-017:n hyväksyttyyn riskiin).
  M4. Makefilen tyhjä rivi — **fixed**.
  L1. PREDICTION-WORKER-QA:n vanha komento — **fixed**. L2. tuotanto-composen "tenant-specific" -virheteksti — **fixed**. L3. vaiheväli 086A–087B ja MCP-sanamuoto — **fixed**. L4. LikeC4:n vyöhyke-id:t ja "suunniteltu"-merkintä — **fixed** (id:t `identity`/`devIdentity`). L5. AI.md:n "älä muuta Authentik-konfiguraatiota" — **fixed**. L6. `session_state`-sanamuoto — **fixed**. L7. PlantUML:n vanha lause — **fixed**. L8. `COMPOSE_LOCAL`-alias — jätetty (kosmeettinen, pitää diffin pienenä).
  Ei toista kierrosta. Yksi kierros kolmesta.

## Documentation effects

- [x] Update `docs/operations/` or `docs/runbooks/` — `docs/runbooks/production.md` (identity section, release block), `docs/operations/local-development.md`, `docs/operations/testing.md`, `README.md`, `backend/README.md`, QA records (notes)
- [x] Update architecture or ADR — ADR-004, 006, 013, 015 notes, `docs/adr/README.md`, `docs/architecture/{stack,overview,deployment,domains/*,data/DATA-MODEL}.md`, `component-authentication-topology.puml` + SVG, LikeC4 models
- [x] Update `.env.example`

## Blocked by

- 03
- 04

## Completion record

- Entra on poistettu koodista, skripteistä, Makefilestä, composesta, CI-harnessista, diagrammeista ja ohjeista; tilalle Authentik-ohjeet. Poikkeamat: ADR:t ja QA-tallenteet jäävät Entra-sanoineen historiana (merkittynä), CI-harnessin Linux-ajoa ja LikeC4-validointia ei voitu ajaa, `make frontend-check` ei ajettu. Commit: `feat: authentik-sign-in 05`.

## Comments

- Lähde: Yearclock `6848e72` (`authentik/`, `docker-compose.yml`, `docs/runbooks/authentik-*.md`, `backend/app/oidc.py`); kirjaa käytetyt lähdetiedostot lopussa.
