# Legal documents

The texts live in [`backend/legal/`](../../backend/legal/) (ADR-0041), one copy only. This page explains how to edit
and publish them; the register of documents is in `.scratch/yearclock-v2-legal-documents/research.md`.

## Files

`backend/legal/<key>.<locale>.md`, where the key is one of `terms`, `dpa`, `privacy`, `storage`, `subprocessors`,
`switching`, `security`, `provider` and the locale is `fi` or `en`. Each starts with:

```text
---
title: Data processing agreement
version: 1
effective_from: 2026-12-01
status: draft
acceptance: required
---
```

- `status: draft` texts are placeholders: never required, never announced, shown only when `LEGAL_SHOW_DRAFTS=true`, and then only to signed-in customers (never to anonymous visitors or search engines).
- `acceptance` is `required` (an Owner accepts for the Organization), `notice` (Owners are told), or `none`.
- Both locales of a key must have the same `version`, `effective_from`, `status`, and `acceptance`; the backend refuses
  to start otherwise, naming the file.
- Use Markdown headings, lists, tables, and links; raw HTML is not rendered.

## Publishing a new version

A lawyer reviews the change; raise `version`, set `effective_from` at least 30 days ahead for a change that needs notice,
set `status: published`, and release. Within an hour every Owner is notified once (in the app and by email, with the 30-day period and the legal contact). Owners accept `required` documents in Organization settings. See [`docs/operations/README.md`](../operations/README.md#legal-documents).
