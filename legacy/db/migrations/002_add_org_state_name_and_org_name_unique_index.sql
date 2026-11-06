ALTER TABLE org_states
    ADD COLUMN name TEXT;

UPDATE org_states
SET name = org_state_key
WHERE name IS NULL;

ALTER TABLE org_states
    ALTER COLUMN name SET NOT NULL;

CREATE UNIQUE INDEX ux_organisations_name_active_ci
    ON organisations (lower(name))
    WHERE deleted_time IS NULL;
