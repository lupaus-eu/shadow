---
status: accepted
---

# Reject stale writes with optimistic concurrency

Mutable Yearclock resources carry a monotonically increasing version, and update or delete requests must identify the version the client loaded. The API rejects stale writes with a conflict response rather than silently overwriting another user's changes. The first release uses refresh-and-retry conflict handling and does not implement real-time collaborative editing or WebSocket synchronization.
