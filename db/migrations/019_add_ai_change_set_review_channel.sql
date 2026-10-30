-- ADR-015 amendment (TASK-069O): a human applies or rejects a submitted AI
-- change set in the Metrics tab (web) or by approving an MCP client's
-- apply_change_set or reject_change_set call (mcp). Record the channel, and
-- for mcp the reviewing client, next to reviewed_by and reviewed_time.

ALTER TABLE ai_change_sets
    ADD COLUMN reviewed_via TEXT,
    ADD COLUMN review_client_id TEXT,
    ADD COLUMN review_client_name TEXT;

-- Every review before this migration went through the Metrics tab.
UPDATE ai_change_sets
SET reviewed_via = 'web'
WHERE reviewed_time IS NOT NULL;

ALTER TABLE ai_change_sets
    ADD CONSTRAINT ck_ai_change_sets_reviewed_via
        CHECK (
            (reviewed_via IS NULL) = (reviewed_time IS NULL)
            AND (reviewed_via IS NULL OR reviewed_via IN ('web', 'mcp'))
        ),
    ADD CONSTRAINT ck_ai_change_sets_review_client
        CHECK (
            (review_client_id IS NULL) = (review_client_name IS NULL)
            AND COALESCE(reviewed_via = 'mcp', false) = (review_client_id IS NOT NULL)
        ),
    ADD CONSTRAINT ck_ai_change_sets_review_client_id_non_blank
        CHECK (review_client_id ~ '[^[:space:]]'),
    ADD CONSTRAINT ck_ai_change_sets_review_client_name_length
        CHECK (length(review_client_name) BETWEEN 1 AND 100);

COMMENT ON TABLE ai_change_sets IS
    'AI change sets staged through MCP. A human applies or rejects them in the Metrics tab or by approving an MCP client call; reviewed_via records which. Down migration destroys this history.';
