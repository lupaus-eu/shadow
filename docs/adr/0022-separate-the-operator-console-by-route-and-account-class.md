---
status: accepted
---

# Separate the operator console by route and account class

The first-release operator console shares the React and FastAPI deployment but uses dedicated `/platform/` UI and `/api/v1/platform/` API namespaces, a separate layout, and Platform User-only authorization. It has no customer Organization context and cannot expose customer content without an active approved Support Access grant. A separate deployment remains an option if future scale or security policy requires stronger process isolation.
