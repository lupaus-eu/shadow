ALTER TABLE timeseries
    ADD COLUMN short_name TEXT;

CREATE UNIQUE INDEX ux_timeseries_scenario_short_name_active
    ON timeseries (scenario_id, short_name)
    WHERE deleted_time IS NULL AND short_name IS NOT NULL;

CREATE UNIQUE INDEX ux_timeseries_scenario_name_active
    ON timeseries (scenario_id, lower(btrim(name)))
    WHERE deleted_time IS NULL;
