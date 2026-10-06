ALTER TABLE prediction_model_results
    DROP CONSTRAINT prediction_model_results_result_kind_check,
    ADD CONSTRAINT prediction_model_results_result_kind_check
        CHECK (result_kind IN (
            'naive',
            'seasonal_naive',
            'average',
            'mlforecast',
            'sarima',
            'prophet'
        ));
