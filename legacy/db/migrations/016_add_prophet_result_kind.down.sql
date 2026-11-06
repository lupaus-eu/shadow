DELETE FROM prediction_points
WHERE prediction_model_result_id IN (
    SELECT prediction_model_result_id
    FROM prediction_model_results
    WHERE result_kind = 'prophet'
);

DELETE FROM prediction_model_results
WHERE result_kind = 'prophet';

ALTER TABLE prediction_model_results
    DROP CONSTRAINT prediction_model_results_result_kind_check,
    ADD CONSTRAINT prediction_model_results_result_kind_check
        CHECK (result_kind IN (
            'naive',
            'seasonal_naive',
            'average',
            'mlforecast',
            'sarima'
        ));
