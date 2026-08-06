ALTER TABLE org_states
    ALTER COLUMN target_date DROP NOT NULL;

ALTER TABLE events
    ALTER COLUMN target_date DROP NOT NULL;
