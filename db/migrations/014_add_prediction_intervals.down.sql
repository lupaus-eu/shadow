TRUNCATE TABLE prediction_versions CASCADE;

ALTER TABLE prediction_points
    DROP CONSTRAINT ck_prediction_points_complete_interval,
    DROP COLUMN lower_bound,
    DROP COLUMN upper_bound;

ALTER TABLE prediction_model_results
    DROP CONSTRAINT ck_prediction_model_results_interval_status,
    DROP COLUMN prediction_interval_status,
    DROP COLUMN prediction_interval_reason;

ALTER TABLE prediction_versions
    DROP CONSTRAINT ck_prediction_versions_confidence_level,
    DROP COLUMN confidence_level;
