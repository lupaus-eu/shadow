TRUNCATE TABLE prediction_versions CASCADE;

ALTER TABLE prediction_versions
    DROP CONSTRAINT prediction_versions_cutoff_mode_check,
    ADD CONSTRAINT prediction_versions_cutoff_mode_check
        CHECK (cutoff_mode IN ('asOfStart', 'allCurrentReality'));

ALTER TABLE prediction_targets
    ADD COLUMN reality_scenario_key TEXT NOT NULL DEFAULT 'reality';

ALTER TABLE prediction_targets
    ALTER COLUMN reality_scenario_key DROP DEFAULT;
