---
status: accepted
---

# Keep Yearclock V1 Event-only

Yearclock V1 uses Event as the only dated content in a Lane and removes the
previous Plan Item and Task model. An Event may describe expected work, but it
remains planning intent without assignment, due-date, completion, overdue, or
execution state. This keeps the annual planning surface simple and avoids
locking a future recommendation-driven Task workflow into a model designed
before its system boundary is understood.

Recommendations, simulation, External Signals, and any Task creation or
integration remain outside V1. Event recurrence and exception behavior remain
in scope, and the optional Event URL can link to related work without defining
a Task contract.
