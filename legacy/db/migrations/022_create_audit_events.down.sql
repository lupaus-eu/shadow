DROP TRIGGER audit_events_no_truncate ON audit_events;
DROP TRIGGER audit_events_append_only ON audit_events;
DROP FUNCTION reject_audit_event_mutation();
DROP TABLE audit_events;
