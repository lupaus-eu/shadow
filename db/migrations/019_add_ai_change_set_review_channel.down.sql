-- Drops the review channel and the reviewing MCP client of every reviewed
-- change set. The reviewer, review time and note stay.
ALTER TABLE ai_change_sets
    DROP CONSTRAINT ck_ai_change_sets_review_client_name_length,
    DROP CONSTRAINT ck_ai_change_sets_review_client_id_non_blank,
    DROP CONSTRAINT ck_ai_change_sets_review_client,
    DROP CONSTRAINT ck_ai_change_sets_reviewed_via,
    DROP COLUMN review_client_name,
    DROP COLUMN review_client_id,
    DROP COLUMN reviewed_via;

COMMENT ON TABLE ai_change_sets IS
    'AI change sets staged through MCP. Only a human applies or rejects them. Down migration destroys this history.';
