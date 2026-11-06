# Privacy and data protection

This directory records what personal data Shadow processes, where it is kept,
and how long, together with the related compliance material (records of
processing, breach procedure, staff access policy). It is an engineering
inventory, not legal advice.

Planned processor: Scaleway Transactional Email, for notification and
transactional email (recipient address, subject and text), once the platform
worker runs in production (ADR-019). Nothing is sent to it today. Retention that the code already enforces:
notifications 90 days (`NOTIFICATION_RETENTION_DAYS`), finished outbox emails with
address and text 7 days (`OUTBOX_RETENTION_DAYS`).

No inventory has been written yet. Yearclock's `docs/gdpr/` is the model to
follow; add the inventory when a feature changes personal data, retention, or
a processor.
