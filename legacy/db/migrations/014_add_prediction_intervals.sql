TRUNCATE TABLE prediction_versions CASCADE;

ALTER TABLE prediction_versions
    ADD COLUMN confidence_level INTEGER NOT NULL DEFAULT 80,
    ADD CONSTRAINT ck_prediction_versions_confidence_level
        CHECK (confidence_level BETWEEN 50 AND 99);

ALTER TABLE prediction_model_results
    ADD COLUMN prediction_interval_status TEXT NOT NULL,
    ADD COLUMN prediction_interval_reason TEXT,
    ADD CONSTRAINT ck_prediction_model_results_interval_status
        CHECK (prediction_interval_status IN (
            'available',
            'unavailable',
            'not_applicable'
        ));

ALTER TABLE prediction_points
    ADD COLUMN lower_bound DOUBLE PRECISION,
    ADD COLUMN upper_bound DOUBLE PRECISION,
    ADD CONSTRAINT ck_prediction_points_complete_interval CHECK (
        (lower_bound IS NULL AND upper_bound IS NULL)
        OR (
            lower_bound IS NOT NULL
            AND upper_bound IS NOT NULL
            AND lower_bound <> 'NaN'::float8
            AND lower_bound <> 'Infinity'::float8
            AND lower_bound <> '-Infinity'::float8
            AND upper_bound <> 'NaN'::float8
            AND upper_bound <> 'Infinity'::float8
            AND upper_bound <> '-Infinity'::float8
            AND lower_bound <= value
            AND value <= upper_bound
        )
    );
