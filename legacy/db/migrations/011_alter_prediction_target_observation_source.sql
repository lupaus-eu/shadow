TRUNCATE TABLE prediction_versions CASCADE;

ALTER TABLE prediction_versions
    DROP CONSTRAINT prediction_versions_cutoff_mode_check,
    ADD CONSTRAINT prediction_versions_cutoff_mode_check
        CHECK (cutoff_mode IN ('asOfStart', 'allCurrentScenario'));

ALTER TABLE prediction_targets
    DROP COLUMN reality_scenario_key;
