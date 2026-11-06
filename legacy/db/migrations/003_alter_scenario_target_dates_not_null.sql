DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM org_states WHERE target_date IS NULL) THEN
        RAISE EXCEPTION 'Cannot set org_states.target_date NOT NULL: null values exist';
    END IF;

    IF EXISTS (SELECT 1 FROM events WHERE target_date IS NULL) THEN
        RAISE EXCEPTION 'Cannot set events.target_date NOT NULL: null values exist';
    END IF;
END $$;

ALTER TABLE org_states
    ALTER COLUMN target_date SET NOT NULL;

ALTER TABLE events
    ALTER COLUMN target_date SET NOT NULL;
