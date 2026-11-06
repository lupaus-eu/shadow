DROP INDEX ux_organisations_name_active_ci;

ALTER TABLE org_states
    DROP COLUMN name;
