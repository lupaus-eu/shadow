---
status: accepted
---

# Keep the legal texts in `backend/legal/` and serve them publicly

## Context

Yearclock sells to business customers and must publish its terms, data processing agreement, privacy notice, and
related texts in Finnish and English, version them, and record who accepted which version
(`.scratch/yearclock-v2-legal-documents/`). The images build from `./backend` and `./frontend` only, so a folder such
as `docs/legal/` cannot reach the running service, and the backend needs the versions to enforce acceptance.

## Decision

- The single source of each text is a Markdown file `backend/legal/<key>.<locale>.md` with front matter (`title`,
  `version`, `effective_from`, `status`, `acceptance`). The keys are fixed: `terms`, `dpa`, `privacy`, `storage`,
  `subprocessors`, `switching`, `security`, `provider`; the locales are `fi` and `en`.
- A loader validates the whole set at start-up and the backend refuses to start on a malformed one, naming the
  file. A `draft` text is never required or announced and is served only when `LEGAL_SHOW_DRAFTS` is true and only to a signed-in customer (amended 2026-11-06 for the alpha: drafts are never public).
- Two public, unauthenticated endpoints serve the texts (`/api/v1/legal/documents`). The frontend renders the Markdown
  with `react-markdown` (no raw HTML) and `remark-gfm` for tables.
- A lawyer writes or reviews the text; git history is the version history. `docs/legal/README.md` explains the
  editing and publishing steps and points here.
- A CMS or database editor was rejected (git is simpler and auditable, and the texts change rarely).

## Consequences

- The texts ship with the backend image: publishing a new version is a release.
- Two new frontend dependencies (`react-markdown`, `remark-gfm`), added with ticket 02.
- Tickets 03 and 05 add acceptance records and the announcement of new versions on this base.
