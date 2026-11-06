-- Destructive for prediction request history. Stop every prediction worker before use.
-- Existing prediction versions and all version-owned rows are intentionally preserved.
DROP TABLE prediction_requests;

ALTER TABLE prediction_versions
    DROP CONSTRAINT uq_prediction_versions_id_organisation;
