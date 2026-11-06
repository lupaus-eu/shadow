---
status: accepted
---

# Remove Area and scope access to Yearclocks

Organizations own Yearclocks directly, and Editor and Viewer permissions are assigned per Yearclock. Lanes provide concentric visual structure inside a Yearclock but never define authorization. The redundant Area wrapper is eliminated; this supersedes ADR-0003 only where it assigned External Signals and response permissions through Areas, which are now assigned directly through Yearclocks.

Partially supersedes ADR-0003.

Yearclock V2 (2026-09-25) adds Linked Lanes: one Yearclock can show another Yearclock's Lane live and read only. This keeps the decision. A link grants and restricts nothing: each viewer sees a Linked Lane's content only when their own Organization role or Yearclock grant lets them read the source Yearclock, checked on every read.
