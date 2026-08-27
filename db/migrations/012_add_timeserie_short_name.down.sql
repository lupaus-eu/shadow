DROP INDEX ux_timeseries_scenario_name_active;
DROP INDEX ux_timeseries_scenario_short_name_active;

ALTER TABLE timeseries
    DROP COLUMN short_name;
